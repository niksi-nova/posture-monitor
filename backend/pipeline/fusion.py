"""
fusion.py
=========
Quality-weighted late fusion of sensor and vision model probability vectors.

Both the sensor model and the vision LSTM independently produce a 3-class
probability vector over [good, slouch, forward_head].  This module combines
them in a weighted average, where each model's weight is determined by a
real-time quality score:

  - Vision quality  : the MediaPipe landmark visibility score (0–1)
  - Sensor quality  : how stable the sensor deltas are (low std_dev → high quality)

If only one modality is available (e.g. camera off), that modality receives
full weight.  Alerts are fired only when the fused confidence exceeds a
configurable threshold and enough time has elapsed since the last alert.

Usage::
    from pipeline.fusion import FusionEngine
    import numpy as np

    engine = FusionEngine(alert_threshold=0.75)
    result = engine.predict(
        vision_probs=np.array([0.1, 0.7, 0.2]),
        sensor_probs=np.array([0.2, 0.6, 0.2]),
        visibility=0.85,
        sensor_delta=np.array([-0.05, -0.12, -0.15]),
    )
    print(result["posture"], result["confidence"], result["alert"])
"""

import logging
import time
from typing import Dict, Optional

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_ALERT_THRESHOLD = 0.5    # Confidence threshold to trigger a posture alert (lowered for testing)
ALERT_COOLDOWN_S = 3.0           # Minimum seconds between consecutive alerts (reduced for testing)
CLASS_NAMES = ["good", "slouch", "forward_head"]
GOOD_CLASS_IDX = 0               # Index of the "good" class in CLASS_NAMES

# Clamp bounds for user-configurable alert threshold
_THRESHOLD_MIN = 0.5
_THRESHOLD_MAX = 0.99

# Minimum weight assigned to either modality (avoids division-by-zero / zeroing)
_MIN_WEIGHT = 1e-6


# ---------------------------------------------------------------------------
# FusionEngine
# ---------------------------------------------------------------------------

class FusionEngine:
    """
    Combines vision and sensor model outputs using quality-weighted fusion.

    Attributes:
        threshold:        Confidence threshold above which alerts are fired.
        _last_alert_time: Monotonic timestamp of the most recent alert (or 0.0).
    """

    def __init__(self, alert_threshold: float = DEFAULT_ALERT_THRESHOLD) -> None:
        """
        Initialise the fusion engine with a configurable alert threshold.

        Args:
            alert_threshold: Minimum fused confidence to trigger an alert.
                             Clamped to [0.5, 0.99].
        """
        self.threshold: float = float(
            np.clip(alert_threshold, _THRESHOLD_MIN, _THRESHOLD_MAX)
        )
        self._last_alert_time: float = 0.0   # 0.0 → no alert has been sent yet
        logger.info(
            "FusionEngine initialised (threshold=%.2f, cooldown=%.1f s).",
            self.threshold,
            ALERT_COOLDOWN_S,
        )

    # ------------------------------------------------------------------
    # Core prediction
    # ------------------------------------------------------------------

    def predict(
        self,
        vision_probs: Optional[np.ndarray],
        sensor_probs: Optional[np.ndarray],
        visibility: float,
        sensor_delta: np.ndarray,
    ) -> Dict:
        """
        Fuse vision and sensor probability vectors and determine posture + alert.

        At least one of vision_probs or sensor_probs must be provided.

        Args:
            vision_probs:  3-element numpy array [p_good, p_slouch, p_fwd_head]
                           from the LSTM vision model, or None if unavailable.
            sensor_probs:  3-element numpy array from the sensor SVM/MLP model,
                           or None if unavailable.
            visibility:    MediaPipe landmark visibility in [0, 1].
                           [delta_c, delta_th, delta_l].

        Returns:
            Dict with keys:
              'posture'       — str class name (one of CLASS_NAMES)
              'confidence'    — float in [0, 1]
              'alert'         — bool, True if an alert should be raised
              'probabilities' — Dict[str, float] per-class probabilities
              'weights'       — Dict{'vision': float, 'sensor': float}
              'quality'       — Dict{'vision': float, 'sensor': float}

        Raises:
            ValueError: If both vision_probs and sensor_probs are None.
        """
        if vision_probs is None and sensor_probs is None:
            raise ValueError(
                "FusionEngine.predict(): at least one of vision_probs or "
                "sensor_probs must be provided."
            )

        # --- Compute quality scores ---
        q_vision = float(np.clip(visibility, 0.0, 1.0))

        # Sensor quality: high when deltas are small and stable (low std_dev)
        # Coefficient 5 maps a ±0.2 delta std to roughly a 0 quality drop.
        q_sensor = float(np.clip(1.0 - np.std(sensor_delta) * 5.0, 0.1, 1.0))

        # --- Handle single-modality fallback ---
        if vision_probs is None:
            # Only sensor available → full sensor weight
            p_fused = self._normalise_probs(sensor_probs)
            w_v, w_s = 0.0, 1.0
            q_vision = 0.0
            logger.debug("Fusion: vision unavailable — using sensor only.")
        elif sensor_probs is None:
            # Only vision available → full vision weight
            p_fused = self._normalise_probs(vision_probs)
            w_v, w_s = 1.0, 0.0
            q_sensor = 0.0
            logger.debug("Fusion: sensor unavailable — using vision only.")
        else:
            # Both available — compute normalised quality weights
            total_q = q_vision + q_sensor
            if total_q < _MIN_WEIGHT:
                # Both quality scores are essentially zero — fall back to uniform
                w_v = w_s = 0.5
            else:
                w_v = q_vision / total_q
                w_s = q_sensor / total_q

            # Quality-weighted sum of probability vectors
            p_fused = w_v * self._normalise_probs(vision_probs) + w_s * self._normalise_probs(
                sensor_probs
            )

        # --- Classify ---
        predicted_idx = int(np.argmax(p_fused))
        confidence = float(np.max(p_fused))

        # --- Alert logic ---
        now = time.monotonic()
        time_since_last_alert = now - self._last_alert_time

        alert = (
            predicted_idx != GOOD_CLASS_IDX         # Posture is not "good"
            and confidence >= self.threshold         # High enough confidence
            and time_since_last_alert >= ALERT_COOLDOWN_S  # Cooldown elapsed
        )

        if alert:
            self._last_alert_time = now
            logger.info(
                "Posture alert: '%s' (confidence=%.2f, w_v=%.2f, w_s=%.2f).",
                CLASS_NAMES[predicted_idx],
                confidence,
                w_v,
                w_s,
            )

        return {
            "posture": CLASS_NAMES[predicted_idx],
            "confidence": confidence,
            "alert": alert,
            "probabilities": {
                CLASS_NAMES[i]: float(p_fused[i]) for i in range(len(CLASS_NAMES))
            },
            "weights": {"vision": float(w_v), "sensor": float(w_s)},
            "quality": {"vision": q_vision, "sensor": q_sensor},
        }

    # ------------------------------------------------------------------
    # Threshold management
    # ------------------------------------------------------------------

    def update_threshold(self, t: float) -> None:
        """
        Update the alert confidence threshold, clamped to a safe range.

        Args:
            t: New threshold value.  Will be clamped to [0.5, 0.99].
        """
        self.threshold = float(np.clip(t, _THRESHOLD_MIN, _THRESHOLD_MAX))
        logger.info("FusionEngine alert threshold updated to %.3f.", self.threshold)

    def get_threshold(self) -> float:
        """
        Return the current alert confidence threshold.

        Returns:
            Current threshold as a float in [0.5, 0.99].
        """
        return self.threshold

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_probs(probs: np.ndarray) -> np.ndarray:
        """
        Ensure a probability vector sums to 1 and has no negative values.

        Args:
            probs: Raw probability array of any length.

        Returns:
            Normalised numpy array of the same shape.
        """
        probs = np.clip(np.asarray(probs, dtype=np.float64), 0.0, None)
        total = probs.sum()
        if total < _MIN_WEIGHT:
            # Degenerate vector — return uniform distribution
            return np.ones_like(probs) / len(probs)
        return probs / total


# ---------------------------------------------------------------------------
# Module self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    engine = FusionEngine(alert_threshold=0.6)

    scenarios = [
        {
            "name": "Clear slouch — both models agree",
            "v_probs": np.array([0.05, 0.85, 0.10]),
            "s_probs": np.array([0.10, 0.78, 0.12]),
            "vis": 0.90,
            "delta": np.array([-0.03, -0.15, -0.20]),
        },
        {
            "name": "Forward head — low vision quality",
            "v_probs": np.array([0.20, 0.30, 0.50]),
            "s_probs": np.array([0.10, 0.20, 0.70]),
            "vis": 0.20,
            "delta": np.array([-0.25, -0.05, -0.02]),
        },
        {
            "name": "Good posture",
            "v_probs": np.array([0.80, 0.10, 0.10]),
            "s_probs": np.array([0.75, 0.15, 0.10]),
            "vis": 0.95,
            "delta": np.array([-0.01, 0.00, 0.01]),
        },
        {
            "name": "Sensor only (vision=None)",
            "v_probs": None,
            "s_probs": np.array([0.15, 0.75, 0.10]),
            "vis": 0.0,
            "delta": np.array([-0.05, -0.18, -0.22]),
        },
    ]

    for sc in scenarios:
        result = engine.predict(
            vision_probs=sc["v_probs"],
            sensor_probs=sc["s_probs"],
            visibility=sc["vis"],
            sensor_delta=sc["delta"],
        )
        print(
            f"\n[{sc['name']}]\n"
            f"  Posture     : {result['posture']}\n"
            f"  Confidence  : {result['confidence']:.3f}\n"
            f"  Alert       : {result['alert']}\n"
            f"  Probs       : {result['probabilities']}\n"
            f"  Weights     : {result['weights']}\n"
            f"  Quality     : {result['quality']}"
        )
