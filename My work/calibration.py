"""
calibration.py
---------------
Active calibration routine: asks the user to sit upright, averages sensor
readings over a 10-second window, and saves the result as baseline.json.

This baseline is later used to compute a normalized deviation vector
(live reading - baseline) that feeds the sensor ML model.

Usage:
    python calibration.py
"""

import json
import time
import os
from sensor_reader import SensorReader, SENSOR_KEYS

CALIBRATION_DURATION_SEC = 10
OUTPUT_PATH = os.path.join("data", "baseline.json")


def run_calibration(port=None):
    reader = SensorReader(port=port)

    print("=" * 50)
    print("POSTURE CALIBRATION")
    print("=" * 50)
    print("Sit upright in your normal 'good posture' position.")
    input("Press Enter when ready to begin 10-second calibration...")

    print("Calibrating... hold still and stay upright.")

    sums = {k: 0.0 for k in SENSOR_KEYS}
    count = 0
    start_time = time.time()

    stream = reader.stream()
    while time.time() - start_time < CALIBRATION_DURATION_SEC:
        reading = next(stream)
        for k in SENSOR_KEYS:
            sums[k] += reading[k]
        count += 1

        remaining = CALIBRATION_DURATION_SEC - (time.time() - start_time)
        print(f"\r  ...{remaining:4.1f}s remaining", end="", flush=True)

    print("\nCalibration complete.")

    if count == 0:
        raise RuntimeError("No sensor data received during calibration. Check ESP32 connection.")

    baseline = {k: sums[k] / count for k in SENSOR_KEYS}
    baseline["samples_used"] = count
    baseline["calibrated_at"] = time.time()

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(baseline, f, indent=2)

    print(f"\nBaseline saved to {OUTPUT_PATH}:")
    for k in SENSOR_KEYS:
        print(f"  {k}: {baseline[k]:.1f}")

    reader.close()
    return baseline


def load_baseline(path=OUTPUT_PATH):
    """Helper for other scripts (e.g. fusion.py) to load the saved baseline."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No baseline found at {path}. Run calibration.py first."
        )
    with open(path, "r") as f:
        return json.load(f)


if __name__ == "__main__":
    run_calibration()
