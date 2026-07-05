"""
vision_pipeline.py
==================
MediaPipe Pose pipeline running in a background daemon thread.

Captures webcam frames at TARGET_FPS, processes them with MediaPipe Pose, and
extracts four geometric features per frame:
  - fwd_head_ratio   : forward head distance relative to shoulder width
  - shoulder_tilt    : vertical misalignment of shoulders relative to width
  - torso_lean       : torso height (hip→shoulder) relative to shoulder width
  - ear_sh_ratio     : ear-midpoint to shoulder-midpoint distance relative to
                       shoulder width (proxy for neck tilt)

Features are stored in a sliding window deque of length WINDOW_SIZE=15.
Thread-safe access is provided via get_state(), which returns the window padded
with zeros if fewer than WINDOW_SIZE frames have been collected.

Usage::
    start_pipeline()          # start background thread
    state = get_pipeline().get_state()   # retrieve latest window + metadata
"""

import logging
import math
import threading
import time
from collections import deque
from typing import Dict, List, Optional

import cv2
import mediapipe as mp
import numpy as np

# ---------------------------------------------------------------------------
# MediaPipe is imported lazily inside VisionPipeline.__init__ to avoid
# AttributeError on mediapipe 0.10.x where mp.solutions is not guaranteed
# to be populated at module import time on all platforms.
# ---------------------------------------------------------------------------
mp_pose = None
mp_drawing = None
mp_drawing_styles = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TARGET_FPS = 30                      # Frames per second to target from webcam
WINDOW_SIZE = 15                     # Sliding window length in frames
CAMERA_INDEX = 0                     # Default webcam index
MIN_DETECTION_CONFIDENCE = 0.5       # MediaPipe minimum detection confidence
MIN_TRACKING_CONFIDENCE = 0.5        # MediaPipe minimum tracking confidence

# MediaPipe Pose landmark indices (from the 33-landmark model)
LM_NOSE = 0
LM_LEFT_EAR = 7
LM_RIGHT_EAR = 8
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12
LM_LEFT_HIP = 23
LM_RIGHT_HIP = 24

# Feature vector length (must match the 4 features extracted below)
FEATURE_DIM = 4


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _dist2d(ax: float, ay: float, bx: float, by: float) -> float:
    """
    Euclidean distance between two 2-D points (normalised image coordinates).

    Args:
        ax: x-coordinate of point A.
        ay: y-coordinate of point A.
        bx: x-coordinate of point B.
        by: y-coordinate of point B.

    Returns:
        Euclidean distance as a float.
    """
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def extract_features(landmarks) -> Optional[Dict]:
    """
    Compute posture geometry features from a MediaPipe pose landmark object.

    Args:
        landmarks: mediapipe.framework.formats.landmark_pb2.NormalizedLandmarkList
                   or None.

    Returns:
        Dict with keys 'features' (List[float] length 4) and 'visibility' (float),
        or None if landmarks is None or geometry is degenerate.
    """
    if landmarks is None:
        return None

    lm = landmarks.landmark  # type: ignore[attr-defined]

    # Extract individual landmark coordinates
    nose       = lm[LM_NOSE]
    ear_l      = lm[LM_LEFT_EAR]
    ear_r      = lm[LM_RIGHT_EAR]
    sh_l       = lm[LM_LEFT_SHOULDER]
    sh_r       = lm[LM_RIGHT_SHOULDER]
    hip_l      = lm[LM_LEFT_HIP]
    hip_r      = lm[LM_RIGHT_HIP]

    # Shoulder width in normalised image space — used as the scale reference
    shoulder_width = _dist2d(sh_l.x, sh_l.y, sh_r.x, sh_r.y)
    if shoulder_width < 0.01:
        # Degenerate case: person is side-on or too far from camera
        return None

    # Midpoints (normalised coordinates)
    mid_sh_x = (sh_l.x + sh_r.x) / 2.0
    mid_sh_y = (sh_l.y + sh_r.y) / 2.0
    mid_hip_x = (hip_l.x + hip_r.x) / 2.0
    mid_hip_y = (hip_l.y + hip_r.y) / 2.0
    mid_ear_x = (ear_l.x + ear_r.x) / 2.0
    mid_ear_y = (ear_l.y + ear_r.y) / 2.0

    # --- Feature 1: Forward head ratio ---
    # Horizontal distance of the nose from the shoulder midpoint, normalised.
    # Larger value → head is more forward relative to the torso.
    fwd_head_ratio = _dist2d(nose.x, nose.y, mid_sh_x, mid_sh_y) / shoulder_width

    # --- Feature 2: Shoulder tilt ---
    # Vertical height difference between the two shoulders (absolute), normalised.
    # Non-zero tilt indicates lateral lean or scoliosis-like pattern.
    shoulder_tilt = abs(sh_l.y - sh_r.y) / shoulder_width

    # --- Feature 3: Torso lean ---
    # Distance from hip midpoint to shoulder midpoint, normalised.
    # Shorter distance relative to shoulder width may indicate slouching.
    torso_lean = _dist2d(mid_hip_x, mid_hip_y, mid_sh_x, mid_sh_y) / shoulder_width

    # --- Feature 4: Ear-shoulder ratio ---
    # Distance from ear midpoint to shoulder midpoint, normalised.
    # Larger ratio → ears are further from shoulders (head tilted / neck extended).
    ear_sh_ratio = _dist2d(mid_ear_x, mid_ear_y, mid_sh_x, mid_sh_y) / shoulder_width

    # Quality metric: minimum visibility across upper-body landmarks (hips usually not visible on webcam)
    visibility = float(
        min(sh_l.visibility, sh_r.visibility, nose.visibility)
    )

    return {
        "features": [fwd_head_ratio, shoulder_tilt, torso_lean, ear_sh_ratio],
        "visibility": visibility,
    }


# ---------------------------------------------------------------------------
# VisionPipeline
# ---------------------------------------------------------------------------

class VisionPipeline:
    """
    Background-threaded MediaPipe Pose feature extractor.

    Captures from the configured webcam, processes each frame, and maintains a
    sliding window deque of the last WINDOW_SIZE feature vectors.  All public
    methods are thread-safe.
    """

    def __init__(self) -> None:
        """Initialise MediaPipe pose, sliding window, lock, and control event."""
        global mp_pose, mp_drawing, mp_drawing_styles  # noqa: PLW0603
        # Lazy-load mp.solutions here (not at module level) — mediapipe 0.10.x
        # on Windows only populates mp.solutions after the package has been
        # fully imported, so accessing it at module level raises AttributeError.
        if mp_pose is None:
            try:
                mp_pose = mp.solutions.pose
                mp_drawing = mp.solutions.drawing_utils
                mp_drawing_styles = mp.solutions.drawing_styles
            except AttributeError as exc:
                raise RuntimeError(
                    "Cannot access mp.solutions — your mediapipe installation may be "
                    "incompatible. Try: pip install mediapipe==0.10.14"
                ) from exc
        self._pose = mp_pose.Pose(
            min_detection_confidence=MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=MIN_TRACKING_CONFIDENCE,
            model_complexity=1,   # 0=lite, 1=full, 2=heavy
        )
        # Sliding window of feature dicts; each entry: {"features": list, "visibility": float}
        self._window: deque = deque(maxlen=WINDOW_SIZE)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        # Most recently extracted output (includes timestamp)
        self._last_output: Dict = {
            "features": [[0.0] * FEATURE_DIM] * WINDOW_SIZE,
            "visibility": 0.0,
            "timestamp_ms": 0.0,
            "frame_count": 0,
        }
        self._latest_jpeg: Optional[bytes] = None
        self._camera_available: bool = False

    # ------------------------------------------------------------------
    # Internal thread loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """
        Background thread: continuously capture frames and extract features.

        Opens the webcam, reads frames in a loop, and writes extracted features
        into the sliding window.  Throttles to TARGET_FPS using time.sleep.
        """
        cap = cv2.VideoCapture(CAMERA_INDEX)
        if not cap.isOpened():
            logger.error(
                "VisionPipeline: cannot open camera index %d.", CAMERA_INDEX
            )
            self._camera_available = False
            return

        self._camera_available = True
        logger.info("VisionPipeline: camera %d opened at target %d fps.", CAMERA_INDEX, TARGET_FPS)

        frame_period_s = 1.0 / TARGET_FPS
        frame_count = 0

        while not self._stop_event.is_set():
            loop_start = time.monotonic()

            ret, frame = cap.read()
            if not ret:
                logger.warning("VisionPipeline: failed to read frame — skipping.")
                time.sleep(frame_period_s)
                continue

            # Mirror horizontally so the display is more intuitive (selfie view)
            frame = cv2.flip(frame, 1)

            # MediaPipe requires RGB input
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb_frame.flags.writeable = False   # Minor performance hint for MediaPipe
            results = self._pose.process(rgb_frame)
            rgb_frame.flags.writeable = True

            feature_dict = extract_features(results.pose_landmarks)
            timestamp_ms = time.monotonic() * 1_000.0

            # Draw landmarks for video feed
            if results.pose_landmarks and mp_drawing and mp_drawing_styles and mp_pose:
                mp_drawing.draw_landmarks(
                    frame,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style(),
                )
            
            # Encode frame to JPEG for streaming
            ret_jpg, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            jpeg_bytes = jpeg.tobytes() if ret_jpg else None

            with self._lock:
                if feature_dict is not None:
                    self._window.append(feature_dict)
                frame_count += 1
                self._latest_jpeg = jpeg_bytes
                # Rebuild the padded window snapshot
                self._last_output = self._build_output(timestamp_ms, frame_count)

            # Throttle loop to target FPS
            elapsed = time.monotonic() - loop_start
            sleep_s = max(0.0, frame_period_s - elapsed)
            time.sleep(sleep_s)

        cap.release()
        logger.info("VisionPipeline: camera released.")

    def _build_output(self, timestamp_ms: float, frame_count: int) -> Dict:
        """
        Construct the output dict from the current window state.

        Pads the feature list with zero vectors if fewer than WINDOW_SIZE frames
        have been collected.

        Args:
            timestamp_ms: Current monotonic time in milliseconds.
            frame_count:  Total frames processed so far.

        Returns:
            Dict with keys 'features', 'visibility', 'timestamp_ms', 'frame_count'.
        """
        window_list = list(self._window)  # snapshot of current deque contents

        # Pad with zero vectors on the left so shape is always (WINDOW_SIZE, 4)
        pad_count = WINDOW_SIZE - len(window_list)
        padded_features: List[List[float]] = (
            [[0.0] * FEATURE_DIM] * pad_count
            + [entry["features"] for entry in window_list]
        )

        # Use the latest frame's visibility; 0 if no frames yet
        visibility = window_list[-1]["visibility"] if window_list else 0.0

        return {
            "features": padded_features,
            "visibility": visibility,
            "timestamp_ms": timestamp_ms,
            "frame_count": frame_count,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Launch the frame-capture loop in a background daemon thread.

        The thread is daemonised so it will not block program exit.
        """
        self._stop_event.clear()
        thread = threading.Thread(target=self._run_loop, name="VisionPipeline", daemon=True)
        thread.start()
        logger.info("VisionPipeline: background thread started.")

    def stop(self) -> None:
        """
        Signal the background thread to stop processing.

        The thread will exit after it finishes the current frame.
        """
        self._stop_event.set()
        logger.info("VisionPipeline: stop signal sent.")

    def get_state(self) -> Dict:
        """
        Thread-safe retrieval of the most recent windowed feature output.

        If the window has fewer than WINDOW_SIZE frames, missing positions are
        padded with zero vectors (left-pad, most recent frames on the right).

        Returns:
            Dict with keys:
              'features'     — List[List[float]] of shape (WINDOW_SIZE, 4)
              'visibility'   — float in [0, 1]
              'timestamp_ms' — float, monotonic ms
              'frame_count'  — int
        """
        with self._lock:
            # Return a shallow copy to avoid race conditions in callers
            output = dict(self._last_output)
            output["features"] = [list(row) for row in output["features"]]
        return output

    def get_latest_jpeg(self) -> Optional[bytes]:
        """Thread-safe retrieval of the latest JPEG frame."""
        with self._lock:
            return self._latest_jpeg

    def is_camera_available(self) -> bool:
        """
        Return whether the camera was successfully opened.

        Returns:
            True if the webcam is (or was) open; False if it failed to open.
        """
        return self._camera_available


# ---------------------------------------------------------------------------
# Module-level singleton helpers
# ---------------------------------------------------------------------------

_pipeline: Optional[VisionPipeline] = None
_pipeline_lock = threading.Lock()


def get_pipeline() -> Optional[VisionPipeline]:
    """
    Return the module-level VisionPipeline singleton.

    Returns:
        The singleton VisionPipeline instance, or None if not yet started.
    """
    return _pipeline


def start_pipeline() -> VisionPipeline:
    """
    Create (if necessary) and start the module-level VisionPipeline singleton.

    Thread-safe: safe to call from multiple threads simultaneously.

    Returns:
        The running VisionPipeline singleton.
    """
    global _pipeline  # noqa: PLW0603
    with _pipeline_lock:
        if _pipeline is None:
            _pipeline = VisionPipeline()
            _pipeline.start()
            logger.info("Module-level VisionPipeline singleton created and started.")
        else:
            logger.debug("start_pipeline(): singleton already running.")
    return _pipeline


# ---------------------------------------------------------------------------
# Module self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("Starting VisionPipeline self-test (5 seconds) …")
    pipeline = start_pipeline()
    time.sleep(1.0)  # Allow the background thread a moment to open the camera

    if not pipeline.is_camera_available():
        print("Camera not available — cannot run live self-test.")
        sys.exit(1)

    for _ in range(5):
        state = pipeline.get_state()
        vis = state["visibility"]
        frame_count = state["frame_count"]
        latest_features = state["features"][-1] if state["features"] else []
        print(
            f"frame={frame_count:5d}  vis={vis:.2f}  features={latest_features}"
        )
        time.sleep(1.0)

    pipeline.stop()
    print("Self-test complete.")
    sys.exit(0)
