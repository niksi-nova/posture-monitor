"""
calibration.py
==============
10-second calibration routine that collects simultaneous sensor and vision data
from a subject sitting in a known-good neutral posture, then persists the
averaged values as a JSON baseline file.

The calibration baseline is later consumed by:
  - BaselineTracker (sensor_reader.py) for normalised delta computation.
  - FusionEngine (fusion.py) as a reference for detecting deviations.

Typical usage::
    from pipeline.calibration import run_calibration, is_calibrated, load_baseline
    from pipeline.sensor_reader import create_reader
    from pipeline.vision_pipeline import start_pipeline

    reader = create_reader()
    pipeline = start_pipeline()

    result = run_calibration(reader, pipeline, progress_callback=lambda f: print(f"{f*100:.0f}%"))
    print(result)
"""

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CALIBRATION_DURATION_S = 10          # How long to collect calibration data (seconds)
SAMPLE_RATE_HZ = 50                  # Expected sensor sample rate
TARGET_SAMPLES = CALIBRATION_DURATION_S * SAMPLE_RATE_HZ  # 500 sensor samples

# Baseline file location: <project_root>/data/baseline.json
BASELINE_PATH = Path(__file__).parent.parent / "data" / "baseline.json"


# ---------------------------------------------------------------------------
# CalibrationResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class CalibrationResult:
    """
    Stores averaged sensor channel baselines and vision reference features
    captured during a calibration session.

    Attributes:
        cervical:          Mean cervical ADC reading during calibration.
        thoracic:          Mean thoracic ADC reading.
        lumbar:            Mean lumbar ADC reading.
        calibrated_at:     ISO-8601 UTC timestamp of when calibration completed.
        vision_reference:  4-element list of mean vision features [fwd_head_ratio,
                           shoulder_tilt, torso_lean, ear_sh_ratio].
    """

    cervical: float
    thoracic: float
    lumbar: float
    calibrated_at: str
    vision_reference: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])

    def to_dict(self) -> Dict:
        """
        Convert this dataclass to a plain dict for JSON serialisation.

        Returns:
            Dict representation of the calibration result.
        """
        return asdict(self)


# ---------------------------------------------------------------------------
# Core calibration function
# ---------------------------------------------------------------------------

def run_calibration(
    sensor_reader,
    vision_pipeline,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> CalibrationResult:
    """
    Collect CALIBRATION_DURATION_S seconds of data and compute a neutral baseline.

    The subject should be sitting in good posture during this window.

    Sensor samples are pulled at SAMPLE_RATE_HZ; vision frames are collected in
    a background thread at TARGET_FPS (up to 300 frames total for 10 s at 30 fps).

    Args:
        sensor_reader:     An instance of SyntheticSensorReader or RealSensorReader.
        vision_pipeline:   A started VisionPipeline instance (or None to skip vision).
        progress_callback: Optional callable receiving a float in [0, 1] indicating
                           collection progress.  Called once per second.

    Returns:
        CalibrationResult with averaged values saved to BASELINE_PATH.
    """
    logger.info(
        "Starting %d-second calibration — hold still in neutral posture.",
        CALIBRATION_DURATION_S,
    )

    sample_period_s = 1.0 / SAMPLE_RATE_HZ
    start_time = time.monotonic()
    deadline = start_time + CALIBRATION_DURATION_S

    # Accumulators for sensor channels
    acc: Dict[str, List[float]] = {"c": [], "th": [], "l": []}

    # Vision feature accumulator (list of 4-element lists)
    vision_acc: List[List[float]] = []
    last_vision_ts: float = -1.0  # track last vision frame we recorded

    samples_collected = 0
    last_progress_report = start_time

    while time.monotonic() < deadline:
        loop_start = time.monotonic()

        # --- Collect sensor sample ---
        try:
            sample = sensor_reader.get_sample()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sensor read error during calibration: %s", exc)
            sample = None

        if sample is not None:
            for ch in ("c", "th", "l"):
                if ch in sample:
                    acc[ch].append(float(sample[ch]))
            samples_collected += 1

        # --- Collect vision frame (non-blocking) ---
        if vision_pipeline is not None:
            try:
                state = vision_pipeline.get_state()
                ts = state.get("timestamp_ms", -1.0)
                # Only record each unique frame once (avoid duplicate timestamps)
                if ts != last_vision_ts and state.get("visibility", 0.0) > 0.1:
                    latest_features = state["features"][-1]  # most recent frame
                    if any(f != 0.0 for f in latest_features):
                        vision_acc.append(latest_features)
                        last_vision_ts = ts
            except Exception as exc:  # noqa: BLE001
                logger.debug("Vision read error during calibration: %s", exc)

        # --- Progress callback approximately once per second ---
        now = time.monotonic()
        if progress_callback is not None and (now - last_progress_report) >= 1.0:
            fraction = min(1.0, (now - start_time) / CALIBRATION_DURATION_S)
            try:
                progress_callback(fraction)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Progress callback error: %s", exc)
            last_progress_report = now

        # Throttle to sensor sample rate
        elapsed = time.monotonic() - loop_start
        sleep_s = max(0.0, sample_period_s - elapsed)
        time.sleep(sleep_s)

    # Final progress = 1.0
    if progress_callback is not None:
        try:
            progress_callback(1.0)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Progress callback final error: %s", exc)

    logger.info(
        "Calibration collection complete: %d sensor samples, %d vision frames.",
        samples_collected,
        len(vision_acc),
    )

    # --- Compute per-channel means ---
    def _safe_mean(values: List[float], fallback: float) -> float:
        """Return mean of values, or fallback if the list is empty."""
        return sum(values) / len(values) if values else fallback

    # Fallback ADC defaults from the good-posture targets
    from pipeline.sensor_reader import POSTURE_TARGETS  # local import to avoid circularity

    cervical  = _safe_mean(acc["c"],   POSTURE_TARGETS["good"]["c"][0])
    thoracic  = _safe_mean(acc["th"],  POSTURE_TARGETS["good"]["th"][0])
    lumbar    = _safe_mean(acc["l"],   POSTURE_TARGETS["good"]["l"][0])

    # --- Compute vision reference (average each of the 4 features) ---
    if vision_acc:
        vision_arr = [list(row) for row in vision_acc]
        vision_reference: List[float] = [
            sum(row[i] for row in vision_arr) / len(vision_arr)
            for i in range(4)
        ]
    else:
        # Default reference from empirical good-posture observations
        vision_reference = [1.2, 0.02, 1.8, 0.9]
        logger.warning("No vision frames collected — using default vision_reference.")

    result = CalibrationResult(
        cervical=round(cervical, 2),
        thoracic=round(thoracic, 2),
        lumbar=round(lumbar, 2),
        calibrated_at=datetime.now(tz=timezone.utc).isoformat(),
        vision_reference=[round(v, 4) for v in vision_reference],
    )

    # --- Save to disk ---
    _save_baseline(result)
    logger.info("Calibration result: %s", result)
    return result


def _save_baseline(result: CalibrationResult) -> None:
    """
    Persist a CalibrationResult to BASELINE_PATH as JSON.

    Args:
        result: CalibrationResult instance to serialise.
    """
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(BASELINE_PATH, "w", encoding="utf-8") as fh:
            json.dump(result.to_dict(), fh, indent=2)
        logger.info("Baseline saved to %s", BASELINE_PATH)
    except OSError as exc:
        logger.error("Failed to save baseline to %s: %s", BASELINE_PATH, exc)


# ---------------------------------------------------------------------------
# Convenience loaders
# ---------------------------------------------------------------------------

def load_baseline() -> Optional[Dict]:
    """
    Load and return the contents of baseline.json, or None if not found/invalid.

    Returns:
        Dict with calibration data, or None.
    """
    if not BASELINE_PATH.exists():
        logger.info("load_baseline: no baseline file found at %s.", BASELINE_PATH)
        return None
    try:
        with open(BASELINE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        logger.debug("Baseline loaded from %s.", BASELINE_PATH)
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load baseline from %s: %s", BASELINE_PATH, exc)
        return None


def is_calibrated() -> bool:
    """
    Return True if a valid baseline.json exists on disk.

    A file is considered valid if it exists and contains at least the
    'cervical', 'thoracic', and 'lumbar' keys.

    Returns:
        True if calibration file is present and parseable.
    """
    data = load_baseline()
    if data is None:
        return False
    required_keys = {"cervical", "thoracic", "lumbar"}
    return required_keys.issubset(data.keys())


# ---------------------------------------------------------------------------
# Module self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from pipeline.sensor_reader import create_reader
    from pipeline.vision_pipeline import start_pipeline

    print("Running calibration self-test …")
    reader = create_reader()

    # Try to start vision pipeline; proceed without it if camera unavailable
    try:
        vp = start_pipeline()
        import time as _t
        _t.sleep(0.5)
        if not vp.is_camera_available():
            vp = None
            print("No camera — running calibration without vision.")
    except Exception as _exc:
        vp = None
        print(f"Vision pipeline unavailable: {_exc}")

    def progress(f: float) -> None:
        """Print calibration progress as a percentage."""
        bar = "#" * int(f * 20)
        print(f"\r[{bar:<20}] {f*100:.0f}%", end="", flush=True)

    result = run_calibration(reader, vp, progress_callback=progress)
    print(f"\nCalibration complete: {result}")
    print(f"Baseline saved: {is_calibrated()}")
    sys.exit(0)
