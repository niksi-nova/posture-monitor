"""
collect_data.py
===============
Labeled data collection script for posture monitoring.

Two modes of operation:
  1. **Live collection** (default): Reads from real/synthetic sensor and the
     running vision pipeline for SESSION_DURATION_S seconds, labelling every
     sample with the given --label.

  2. **Synthetic generation** (--generate-synthetic): Programmatically creates
     SYNTHETIC_SESSIONS_PER_LABEL sessions of labelled data for each posture
     class without requiring any hardware or webcam.

Output CSVs are written to DATA_DIR/<label>_<session_id>.csv.

CSV column schema (10 columns):
    timestamp, delta_c, delta_th, delta_l,
    fwd_head_ratio, shoulder_tilt, torso_lean, ear_sh_ratio, label

Usage::
    # Live data collection
    python collect_data.py --label good
    python collect_data.py --label slouch --session-id my_session_01

    # Synthetic data generation (for bootstrapping model training)
    python collect_data.py --generate-synthetic
"""

import argparse
import logging
import random
import time
import uuid
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SESSION_DURATION_S = 60                         # Length of one live collection session
SAMPLE_RATE_HZ = 50                             # Sensor sample rate
DATA_DIR = Path(__file__).parent.parent / "data" / "raw"   # Output directory for CSVs
CLASS_NAMES = ["good", "slouch", "forward_head"]

# Synthetic generation settings
SYNTHETIC_SESSIONS_PER_LABEL = 6               # 3 simulated people × 2 sessions each
SYNTHETIC_SAMPLES_PER_SESSION = SESSION_DURATION_S * SAMPLE_RATE_HZ  # 3 000 per CSV

# Default baselines used for delta normalisation (ADC counts)
# These match POSTURE_TARGETS["good"] means in sensor_reader.py
_DEFAULT_BASELINE = {
    "c": 2200.0,
    "th": 2150.0,
    "l": 2300.0,
}

# ---------------------------------------------------------------------------
# Vision feature distributions per posture class
# Each tuple: (mean, std_dev)
# ---------------------------------------------------------------------------
_VISION_PARAMS = {
    "good": {
        "fwd_head_ratio": (1.20, 0.05),
        "shoulder_tilt":  (0.02, 0.01),
        "torso_lean":     (1.80, 0.05),
        "ear_sh_ratio":   (0.90, 0.05),
    },
    "slouch": {
        "fwd_head_ratio": (1.30, 0.07),
        "shoulder_tilt":  (0.04, 0.02),
        "torso_lean":     (2.10, 0.08),
        "ear_sh_ratio":   (0.95, 0.05),
    },
    "forward_head": {
        "fwd_head_ratio": (1.60, 0.08),
        "shoulder_tilt":  (0.03, 0.01),
        "torso_lean":     (1.85, 0.06),
        "ear_sh_ratio":   (1.15, 0.06),
    },
}

# Sensor ADC target distributions per posture class (mean, std_dev)
_SENSOR_PARAMS = {
    "good": {
        "c": (2250.0, 30.0), "th": (2150.0, 30.0),
        "l": (2300.0, 30.0),
    },
    "slouch": {
        "c": (2250.0, 50.0), "th": (1800.0, 40.0),
        "l": (1600.0, 50.0),
    },
    "forward_head": {
        "c": (1500.0, 50.0), "th": (1900.0, 40.0),
        "l": (2250.0, 30.0),
    },
}

# Extra Gaussian noise applied on top of state distributions (simulates subject variance)
_EXTRA_NOISE_STD = 8.0  # ADC counts


# ---------------------------------------------------------------------------
# Synthetic session generator
# ---------------------------------------------------------------------------

def generate_synthetic_session(label: str, session_id: str) -> pd.DataFrame:
    """
    Create a labelled DataFrame of synthetic sensor + vision data for one session.

    The function samples from per-class Gaussian distributions for both sensor
    channels and vision geometry features, adds extra per-sample noise, and
    computes normalised sensor deltas relative to the default baseline.

    Args:
        label:      Posture class label, one of CLASS_NAMES.
        session_id: Unique string identifier for this session (used in logging).

    Returns:
        DataFrame with columns: timestamp, delta_c, delta_th, delta_l,
        fwd_head_ratio, shoulder_tilt, torso_lean, ear_sh_ratio, label.

    Raises:
        ValueError: If label is not in CLASS_NAMES.
    """
    if label not in CLASS_NAMES:
        raise ValueError(f"Unknown label '{label}'. Must be one of {CLASS_NAMES}.")

    n = SYNTHETIC_SAMPLES_PER_SESSION
    sp = _SENSOR_PARAMS[label]   # sensor distribution params for this label
    vp = _VISION_PARAMS[label]   # vision distribution params for this label

    rng = np.random.default_rng()  # independent RNG per session

    # --- Sensor ADC samples (Gaussian + extra noise) ---
    c_adc   = rng.normal(sp["c"][0],   sp["c"][1],   n) + rng.normal(0, _EXTRA_NOISE_STD, n)
    th_adc  = rng.normal(sp["th"][0],  sp["th"][1],  n) + rng.normal(0, _EXTRA_NOISE_STD, n)
    l_adc   = rng.normal(sp["l"][0],   sp["l"][1],   n) + rng.normal(0, _EXTRA_NOISE_STD, n)

    # --- Clamp to valid 12-bit ADC range ---
    c_adc   = np.clip(c_adc,   0, 4095)
    th_adc  = np.clip(th_adc,  0, 4095)
    l_adc   = np.clip(l_adc,   0, 4095)

    # --- Normalised deltas relative to default good-posture baseline ---
    delta_c   = (c_adc   - _DEFAULT_BASELINE["c"])   / _DEFAULT_BASELINE["c"]
    delta_th  = (th_adc  - _DEFAULT_BASELINE["th"])  / _DEFAULT_BASELINE["th"]
    delta_l   = (l_adc   - _DEFAULT_BASELINE["l"])   / _DEFAULT_BASELINE["l"]

    # --- Vision features (Gaussian, clamped to reasonable ranges) ---
    fwd_head_ratio = np.clip(
        rng.normal(vp["fwd_head_ratio"][0], vp["fwd_head_ratio"][1], n), 0.5, 3.0
    )
    shoulder_tilt  = np.clip(
        rng.normal(vp["shoulder_tilt"][0],  vp["shoulder_tilt"][1],  n), 0.0, 0.5
    )
    torso_lean     = np.clip(
        rng.normal(vp["torso_lean"][0],     vp["torso_lean"][1],     n), 0.5, 4.0
    )
    ear_sh_ratio   = np.clip(
        rng.normal(vp["ear_sh_ratio"][0],   vp["ear_sh_ratio"][1],   n), 0.3, 2.0
    )

    # --- Timestamps (seconds since session start at 50 Hz) ---
    timestamps = np.arange(n) / SAMPLE_RATE_HZ

    df = pd.DataFrame({
        "timestamp":      timestamps,
        "delta_c":        delta_c,
        "delta_th":       delta_th,
        "delta_l":        delta_l,
        "fwd_head_ratio": fwd_head_ratio,
        "shoulder_tilt":  shoulder_tilt,
        "torso_lean":     torso_lean,
        "ear_sh_ratio":   ear_sh_ratio,
        "label":          label,
    })

    logger.info(
        "Generated synthetic session '%s' label='%s' — %d samples.", session_id, label, n
    )
    return df


# ---------------------------------------------------------------------------
# Live session collector
# ---------------------------------------------------------------------------

def collect_live_session(
    label: str,
    session_id: str,
    sensor_reader,
    vision_pipeline,
    baseline_tracker,
) -> pd.DataFrame:
    """
    Collect a SESSION_DURATION_S live session of labelled posture data.

    Reads from sensor_reader at ~SAMPLE_RATE_HZ and captures concurrent vision
    features from vision_pipeline (if available).  Normalised deltas are
    computed via baseline_tracker.

    Args:
        label:            Posture class label (one of CLASS_NAMES).
        session_id:       Unique session identifier for logging.
        sensor_reader:    SyntheticSensorReader or RealSensorReader instance.
        vision_pipeline:  Running VisionPipeline instance, or None.
        baseline_tracker: BaselineTracker instance used for delta normalisation.

    Returns:
        DataFrame with the same schema as generate_synthetic_session().
    """
    logger.info(
        "Starting live session '%s' label='%s' (%d s).",
        session_id, label, SESSION_DURATION_S,
    )

    sample_period_s = 1.0 / SAMPLE_RATE_HZ
    deadline = time.monotonic() + SESSION_DURATION_S
    start_time = time.monotonic()

    rows: List[dict] = []
    last_vision_ts: float = -1.0

    while time.monotonic() < deadline:
        loop_start = time.monotonic()

        # --- Sensor sample ---
        try:
            sample = sensor_reader.get_sample()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sensor read error during live session: %s", exc)
            sample = None

        if sample is None:
            time.sleep(sample_period_s)
            continue

        delta = baseline_tracker.get_delta(sample)
        baseline_tracker.update(sample)

        # --- Vision features (latest non-duplicate frame) ---
        vision_features = [0.0, 0.0, 0.0, 0.0]
        if vision_pipeline is not None:
            try:
                state = vision_pipeline.get_state()
                ts = state.get("timestamp_ms", -1.0)
                if ts != last_vision_ts:
                    vision_features = state["features"][-1]
                    last_vision_ts = ts
            except Exception as exc:  # noqa: BLE001
                logger.debug("Vision read error: %s", exc)

        rows.append({
            "timestamp":      sample.get("t", time.monotonic() - start_time),
            "delta_c":        delta.get("c", 0.0),
            "delta_th":       delta.get("th", 0.0),
            "delta_l":        delta.get("l", 0.0),
            "fwd_head_ratio": vision_features[0],
            "shoulder_tilt":  vision_features[1],
            "torso_lean":     vision_features[2],
            "ear_sh_ratio":   vision_features[3],
            "label":          label,
        })

        # Progress update every 10 seconds
        elapsed = time.monotonic() - start_time
        if len(rows) % (SAMPLE_RATE_HZ * 10) == 0:
            logger.info(
                "  Live session progress: %.0f%% (%d samples)",
                100.0 * elapsed / SESSION_DURATION_S,
                len(rows),
            )

        # Throttle to sensor sample rate
        processing_time = time.monotonic() - loop_start
        sleep_s = max(0.0, sample_period_s - processing_time)
        time.sleep(sleep_s)

    df = pd.DataFrame(rows)
    logger.info(
        "Live session '%s' complete — %d samples collected.", session_id, len(df)
    )
    return df


# ---------------------------------------------------------------------------
# CSV persistence helper
# ---------------------------------------------------------------------------

def _save_session_csv(df: pd.DataFrame, label: str, session_id: str) -> Path:
    """
    Save a session DataFrame to a CSV file in DATA_DIR.

    Args:
        df:         Session DataFrame.
        label:      Posture class label (used as filename prefix).
        session_id: Session identifier (used in filename).

    Returns:
        Path to the written CSV file.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filename = DATA_DIR / f"{label}_{session_id}.csv"
    try:
        df.to_csv(filename, index=False)
        logger.info("Session saved to %s", filename)
    except OSError as exc:
        logger.error("Failed to save session CSV to %s: %s", filename, exc)
    return filename


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Parse CLI arguments and run either synthetic generation or live collection.

    Options:
        --label              : Posture class label for live collection.
        --generate-synthetic : Generate all synthetic sessions for all labels.
        --session-id         : Override auto-generated session ID.
    """
    parser = argparse.ArgumentParser(
        description="Posture monitoring data collector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--label",
        choices=CLASS_NAMES,
        default="good",
        help="Posture label for live collection (default: good).",
    )
    parser.add_argument(
        "--generate-synthetic",
        action="store_true",
        help="Generate synthetic CSV data for all labels instead of live collection.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Session ID string (auto-generated UUID if omitted).",
    )
    args = parser.parse_args()

    # Auto-generate session ID if not provided
    session_id = args.session_id or str(uuid.uuid4())[:8]

    if args.generate_synthetic:
        # ----------------------------------------------------------------
        # Synthetic generation mode
        # ----------------------------------------------------------------
        total = len(CLASS_NAMES) * SYNTHETIC_SESSIONS_PER_LABEL
        generated = 0
        for label in CLASS_NAMES:
            for i in range(SYNTHETIC_SESSIONS_PER_LABEL):
                sid = f"syn_{session_id}_{label}_{i:02d}"
                df = generate_synthetic_session(label, sid)
                _save_session_csv(df, label, sid)
                generated += 1
                print(
                    f"[{generated}/{total}] Generated {label} session {i+1}"
                    f"/{SYNTHETIC_SESSIONS_PER_LABEL} -> {DATA_DIR}/{label}_{sid}.csv"
                )
        print(f"\n[OK] Synthetic generation complete - {generated} CSV files in {DATA_DIR}")
    else:
        # ----------------------------------------------------------------
        # Live collection mode
        # ----------------------------------------------------------------
        import sys
        # Lazy imports to avoid hard dependency when running --generate-synthetic
        try:
            from pipeline.sensor_reader import BaselineTracker, create_reader
            from pipeline.vision_pipeline import start_pipeline
        except ImportError as exc:
            logger.error("Cannot import pipeline modules: %s", exc)
            sys.exit(1)

        reader = create_reader()
        baseline_tracker = BaselineTracker()

        # Try to start vision pipeline; skip gracefully if unavailable
        try:
            vp = start_pipeline()
            time.sleep(0.5)  # Give thread a moment to open camera
            if not vp.is_camera_available():
                logger.warning("Camera unavailable — collecting sensor data only.")
                vp = None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vision pipeline unavailable: %s — continuing without.", exc)
            vp = None

        print(
            f"Collecting {SESSION_DURATION_S}s of '{args.label}' data "
            f"(session_id={session_id}) …"
        )
        df = collect_live_session(args.label, session_id, reader, vp, baseline_tracker)
        out_path = _save_session_csv(df, args.label, session_id)
        print(f"\n[OK] Session saved to {out_path} ({len(df)} samples)")


if __name__ == "__main__":
    main()
