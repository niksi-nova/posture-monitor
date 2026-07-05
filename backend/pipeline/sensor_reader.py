"""
sensor_reader.py
================
Simulates ESP32 flex sensor output at 50 Hz in SYNTHETIC mode, or reads real
serial data in REAL mode.

SYNTHETIC mode generates realistic ADC readings for 4 spinal sensor channels:
  c   — cervical spine
  th  — thoracic spine
  l   — lumbar spine
  tlj — thoracolumbar junction

The module interpolates smoothly between posture states using linear
interpolation (lerp), adds a slow sinusoidal drift to simulate temperature /
body-heat baseline shift, applies a moving average (matching firmware), and
samples Gaussian noise per channel.

JSON output contract (same in both modes):
  {
    "t":   <float>  # seconds since reader start
    "c":   <float>  # cervical ADC reading (0-4095)
    "th":  <float>  # thoracic ADC reading
    "l":   <float>  # lumbar ADC reading
    "tlj": <float>  # thoracolumbar junction ADC reading
  }

RealSensorReader expects the ESP32 to emit one JSON line per sample at 50 Hz.
"""

import json
import logging
import math
import random
import time
from collections import deque
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple, Union

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SYNTHETIC = False          # Set to False when real ESP32 hardware is connected
SERIAL_PORT = "COM6"           # Windows: check Device Manager → Ports (COM & LPT)
                               #          macOS/Linux: use /dev/ttyUSB0 or /dev/tty.SLAB_USBtoUART
BAUD_RATE = 115_200
SAMPLE_RATE_HZ = 50          # Target output rate in Hertz
SAMPLE_PERIOD_S = 1.0 / SAMPLE_RATE_HZ

# ---------------------------------------------------------------------------
# Signal-processing constants
# ---------------------------------------------------------------------------
MA_WINDOW = 5               # Moving average window length (mirrors firmware)
EMA_ALPHA = 0.0005          # Slow EMA drift correction coefficient per sample
DRIFT_PERIOD_S = 120.0      # Period of low-frequency drift sine wave (seconds)
DRIFT_AMPLITUDE = 80.0      # ADC-count amplitude of slow sinusoidal drift

# ---------------------------------------------------------------------------
# Alert constants
# ---------------------------------------------------------------------------
MOTOR_ENABLED = True         # Set True to enable vibration motor via serial
# Lerp transition timing
LERP_MIN_S = 2.0             # Minimum posture transition duration (seconds)
LERP_MAX_S = 4.0             # Maximum posture transition duration (seconds)

# ---------------------------------------------------------------------------
# Posture state ADC targets
# Each channel has (mean, std_dev) for Gaussian sampling.
# Keys match ESP32 JSON field names.
# ---------------------------------------------------------------------------
POSTURE_TARGETS: Dict[str, Dict[str, Tuple[float, float]]] = {
    "good": {
        "c":   (2250.0, 30.0),   # cervical — near baseline
        "th":  (2150.0, 30.0),   # thoracic — near baseline
        "l":   (2300.0, 30.0),   # lumbar — near baseline
        "tlj": (2200.0, 30.0),   # thoracolumbar — near baseline
    },
    "slouch": {
        "c":   (2250.0, 50.0),   # cervical stays near baseline
        "th":  (1800.0, 40.0),   # thoracic drops moderately
        "l":   (1600.0, 50.0),   # lumbar drops most
        "tlj": (1650.0, 50.0),   # thoracolumbar drops significantly
    },
    "forward_head": {
        "c":   (1500.0, 50.0),   # cervical drops most
        "th":  (1900.0, 40.0),   # thoracic drops moderately
        "l":   (2250.0, 30.0),   # lumbar near baseline
        "tlj": (2200.0, 30.0),   # thoracolumbar near baseline
    },
}

# Lock the synthetic sensor state to 'good' so it doesn't interfere with live camera tests.
STATE_SEQUENCE = ["good"]
STATE_DURATION_S = (8, 20)  # random state duration range in seconds)

# Ordered channel keys — defines array ordering for MA buffers etc.
_CHANNELS = ["c", "th", "l", "tlj"]


# ---------------------------------------------------------------------------
# BaselineTracker
# ---------------------------------------------------------------------------

class BaselineTracker:
    """
    Tracks slow drift in sensor baseline using an exponential moving average.

    The baseline starts from the "good" posture means or from a saved JSON file.
    After each sample, `update()` nudges the baseline toward the live reading at
    rate EMA_ALPHA.  `get_delta()` returns normalised per-channel deviations.
    """

    def __init__(self, baseline_path: Optional[Path] = None) -> None:
        """
        Initialise baseline from file if it exists, otherwise use default targets.

        Args:
            baseline_path: Optional path to a previously saved baseline.json.
        """
        self._baseline: Dict[str, float] = {
            ch: POSTURE_TARGETS["good"][ch][0] for ch in _CHANNELS
        }
        self._vision_reference = None
        self._calibrated_at = None
        if baseline_path is not None:
            self.load(baseline_path)

    def update(self, sample: Dict[str, float]) -> None:
        """
        Apply EMA update to drift the baseline toward the latest reading.

        Args:
            sample: Dict with channel keys mapping to current ADC float values.
        """
        for ch in _CHANNELS:
            if ch in sample:
                # Slowly shift baseline toward live reading (drift correction)
                self._baseline[ch] = (
                    (1.0 - EMA_ALPHA) * self._baseline[ch] + EMA_ALPHA * sample[ch]
                )

    def get_delta(self, sample: Dict[str, float]) -> Dict[str, float]:
        """
        Return normalised fractional deviation of each channel from baseline.

        Args:
            sample: Dict with channel keys mapping to current ADC float values.

        Returns:
            Dict of {channel: delta} where delta = (live - baseline) / baseline.
        """
        return {
            ch: (sample[ch] - self._baseline[ch]) / max(self._baseline[ch], 1.0)
            for ch in _CHANNELS
            if ch in sample
        }

    def get_baseline(self) -> Dict[str, float]:
        """
        Return a copy of the current baseline dict.

        Returns:
            Dict mapping channel name to baseline ADC value, along with vision reference.
        """
        res = dict(self._baseline)
        if self._vision_reference:
            res["vision_reference"] = self._vision_reference
        if self._calibrated_at:
            res["calibrated_at"] = self._calibrated_at
        return res

    def save(self, path: Path) -> None:
        """
        Persist the current baseline to a JSON file.

        Args:
            path: Destination file path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._baseline, fh, indent=2)
            logger.info("Baseline saved to %s", path)
        except OSError as exc:
            logger.error("Failed to save baseline to %s: %s", path, exc)

    def load(self, path: Path) -> None:
        """
        Load baseline values from a JSON file, replacing current state.

        Args:
            path: Source file path.
        """
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            # Only accept keys we know about to avoid corrupting state
            for ch in _CHANNELS:
                if ch in data:
                    self._baseline[ch] = float(data[ch])
            if "vision_reference" in data:
                self._vision_reference = data["vision_reference"]
            if "calibrated_at" in data:
                self._calibrated_at = data["calibrated_at"]
            logger.info("Baseline loaded from %s", path)
        except FileNotFoundError:
            logger.info("No baseline file at %s — using defaults.", path)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Invalid baseline file %s: %s — using defaults.", path, exc)


# ---------------------------------------------------------------------------
# SyntheticSensorReader
# ---------------------------------------------------------------------------

class SyntheticSensorReader:
    """
    Generates realistic synthetic flex-sensor ADC readings at 50 Hz.

    Behaviour:
    - Cycles through posture states from STATE_SEQUENCE with random hold durations.
    - Smoothly interpolates (lerps) between states over LERP_MIN_S – LERP_MAX_S.
    - Adds a low-frequency sinusoidal drift to simulate temperature baseline drift.
    - Applies per-channel Gaussian noise and a moving average filter.
    """

    def __init__(self) -> None:
        """Initialise ADC values at 'good' targets and set up internal state."""
        # Current interpolated ADC values (float, per channel)
        self._current: Dict[str, float] = {
            ch: POSTURE_TARGETS["good"][ch][0] for ch in _CHANNELS
        }
        # Source values at the start of the current lerp
        self._lerp_src: Dict[str, float] = dict(self._current)
        # Target values at the end of the current lerp
        self._lerp_tgt: Dict[str, float] = dict(self._current)

        # Moving average buffers: one deque per channel, pre-filled with baseline
        self._ma_buffers: Dict[str, deque] = {
            ch: deque([POSTURE_TARGETS["good"][ch][0]] * MA_WINDOW, maxlen=MA_WINDOW)
            for ch in _CHANNELS
        }

        # Lerp progress in [0, 1] and duration in samples
        self._lerp_progress: float = 1.0   # starts at 1.0 → transition immediately
        self._lerp_samples: int = 1         # total samples for this transition

        # Slow sinusoidal drift — independent phase per channel for variety
        self._drift_phases: Dict[str, float] = {
            ch: random.uniform(0.0, 2 * math.pi) for ch in _CHANNELS
        }

        # State machine
        self._current_state: str = "good"
        self._state_deadline: float = time.monotonic() + random.uniform(*STATE_DURATION_S)

        # Wall-clock reference for elapsed-time timestamps
        self._start_time: float = time.monotonic()

        # Sample counter — used to advance drift phase each tick
        self._sample_idx: int = 0

        logger.info("SyntheticSensorReader initialised in state='good'.")

    def _next_state(self) -> None:
        """
        Pick a new posture state (different from the current one) and start lerp.

        The lerp source is snapped to the current ADC values so that transitions
        always look smooth regardless of where mid-transition we are.
        """
        # Choose a different state from the weighted list
        choices = [s for s in STATE_SEQUENCE if s != self._current_state]
        if not choices:
            choices = STATE_SEQUENCE
        
        self._current_state = random.choice(choices)

        # Snap lerp source to current values (avoids pop on re-targeting mid-lerp)
        self._lerp_src = dict(self._current)
        # Target means for the new state
        self._lerp_tgt = {
            ch: POSTURE_TARGETS[self._current_state][ch][0] for ch in _CHANNELS
        }

        # Random transition duration converted to sample count
        lerp_s = random.uniform(LERP_MIN_S, LERP_MAX_S)
        self._lerp_samples = max(1, int(lerp_s * SAMPLE_RATE_HZ))
        self._lerp_progress = 0.0

        logger.debug(
            "State transition → '%s' (lerp %.2f s / %d samples)",
            self._current_state,
            lerp_s,
            self._lerp_samples,
        )

    def _tick(self) -> Dict[str, float]:
        """
        Advance simulation by one sample (1/50 s) and return the sample dict.

        Steps:
        1. Check if current state has expired and trigger a new state.
        2. Advance lerp fraction toward target state.
        3. Add slow sinusoidal drift (per-channel phase offset).
        4. Sample per-channel Gaussian noise scaled by state std_dev.
        5. Apply moving average.
        6. Return {t, c, th, l, tlj}.

        Returns:
            Dict with keys 't', 'c', 'th', 'l', 'tlj'.
        """
        now = time.monotonic()

        # --- State machine ---
        if now >= self._state_deadline:
            self._next_state()
            hold_s = random.uniform(*STATE_DURATION_S)
            self._state_deadline = now + hold_s

        # --- Lerp advancement ---
        if self._lerp_progress < 1.0:
            self._lerp_progress = min(
                1.0, self._lerp_progress + 1.0 / self._lerp_samples
            )
        t_lerp = self._lerp_progress  # alpha in [0,1]

        # --- Drift phase advance (one step per sample) ---
        drift_omega = 2.0 * math.pi / (DRIFT_PERIOD_S * SAMPLE_RATE_HZ)  # rad/sample

        raw: Dict[str, float] = {}
        for ch in _CHANNELS:
            # Linear interpolation between source and target means
            mean_lerped = (
                self._lerp_src[ch] + t_lerp * (self._lerp_tgt[ch] - self._lerp_src[ch])
            )

            # Slow sinusoidal drift (independent phase per channel)
            self._drift_phases[ch] += drift_omega
            drift = DRIFT_AMPLITUDE * math.sin(self._drift_phases[ch])

            # Gaussian noise scaled by current state std_dev
            noise_std = POSTURE_TARGETS[self._current_state][ch][1]
            noise = random.gauss(0.0, noise_std)

            # Combine signal components
            adc_raw = mean_lerped + drift + noise

            # Clamp to valid 12-bit ADC range
            adc_raw = max(0.0, min(4095.0, adc_raw))

            # Update moving average buffer
            self._ma_buffers[ch].append(adc_raw)
            raw[ch] = sum(self._ma_buffers[ch]) / len(self._ma_buffers[ch])

        self._sample_idx += 1
        raw["t"] = now - self._start_time
        return raw

    def get_sample(self) -> Dict[str, float]:
        """
        Return the next synthetic sensor sample without blocking.

        Returns:
            Sample dict with keys 't', 'c', 'th', 'l', 'tlj'.
        """
        return self._tick()

    def run(self, callback: Callable[[Dict[str, float]], None]) -> None:
        """
        Blocking loop: call _tick() at SAMPLE_RATE_HZ and pass each sample to callback.

        The loop compensates for processing time to maintain a stable output rate.

        Args:
            callback: Function accepting a sample dict; called for every sample.
        """
        logger.info("SyntheticSensorReader running at %d Hz.", SAMPLE_RATE_HZ)
        while True:
            loop_start = time.monotonic()
            sample = self._tick()
            try:
                callback(sample)
            except Exception as exc:  # noqa: BLE001
                logger.error("Callback raised an exception: %s", exc)
            # Sleep for the remainder of the sample period to hold 50 Hz
            elapsed = time.monotonic() - loop_start
            sleep_s = max(0.0, SAMPLE_PERIOD_S - elapsed)
            time.sleep(sleep_s)


# ---------------------------------------------------------------------------
# RealSensorReader
# ---------------------------------------------------------------------------

class RealSensorReader:
    """
    Reads live flex-sensor data from an ESP32 over a serial (UART) connection.

    The ESP32 is expected to emit one JSON line per sample, e.g.:
      {"t": 1.234, "c": 2245, "th": 2153, "l": 2298, "tlj": 2205}

    If the serial connection fails, the reader retries with exponential back-off
    up to a maximum back-off interval of 30 seconds.
    """

    _MAX_BACKOFF_S = 30.0   # Cap for exponential back-off delay

    def __init__(self) -> None:
        """Initialise reader; actual port open is deferred to run()."""
        self._ser = None
        self._start_time = time.monotonic()
        logger.info(
            "RealSensorReader configured for %s @ %d baud.", SERIAL_PORT, BAUD_RATE
        )

    def _open_port(self):
        """
        Attempt to open the serial port.

        Returns:
            An open serial.Serial instance.

        Raises:
            ImportError: if pyserial is not installed.
            serial.SerialException: if the port cannot be opened.
        """
        try:
            import serial  # noqa: PLC0415 — lazy import to avoid hard dependency
        except ImportError as exc:
            raise ImportError(
                "pyserial is required for real sensor mode. "
                "Install it with: pip install pyserial"
            ) from exc

        import serial  # re-import for type reference
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2.0)
        logger.info("Serial port %s opened successfully.", SERIAL_PORT)
        return ser

    def _read_line(self, ser) -> Optional[Dict[str, float]]:
        """
        Read one line from the serial port and parse it as JSON.

        Args:
            ser: Open serial.Serial instance.

        Returns:
            Parsed sample dict or None on parse failure.
        """
        try:
            raw_line = ser.readline().decode("utf-8", errors="replace").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Serial read error: %s", exc)
            return None

        if not raw_line:
            return None

        try:
            data = json.loads(raw_line)
            # Validate expected keys
            if not all(k in data for k in ("c", "th", "l", "tlj")):
                logger.debug("Incomplete JSON from ESP32: %s", raw_line)
                return None
            # Inject elapsed time if ESP32 does not provide it
            if "t" not in data:
                data["t"] = time.monotonic() - self._start_time
            return data
        except json.JSONDecodeError as exc:
            logger.debug("JSON parse error: %s — raw: %s", exc, raw_line)
            return None

    def run(self, callback: Callable[[Dict[str, float]], None]) -> None:
        """
        Open serial port and stream samples to callback at native ESP32 rate.

        Implements exponential back-off on connection failure.

        Args:
            callback: Function accepting a sample dict; called for every valid sample.
        """
        backoff_s = 1.0
        while True:
            try:
                ser = self._open_port()
                backoff_s = 1.0  # Reset back-off on successful connection
                logger.info("RealSensorReader streaming from %s.", SERIAL_PORT)
                while True:
                    sample = self._read_line(ser)
                    if sample is not None:
                        try:
                            callback(sample)
                        except Exception as exc:  # noqa: BLE001
                            logger.error("Callback raised an exception: %s", exc)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Serial connection failed: %s. Retrying in %.1f s.", exc, backoff_s
                )
                time.sleep(backoff_s)
                # Exponential back-off capped at _MAX_BACKOFF_S
                backoff_s = min(backoff_s * 2.0, self._MAX_BACKOFF_S)

    def get_sample(self) -> Optional[Dict[str, float]]:
        """
        Read and return a single sample from the serial port (blocking).

        Returns:
            Sample dict or None on failure.
        """
        if self._ser is None:
            try:
                self._ser = self._open_port()
            except Exception as exc:  # noqa: BLE001
                logger.error("Cannot open serial port: %s", exc)
                return None
        return self._read_line(self._ser)


# ---------------------------------------------------------------------------
# Motor alert
# ---------------------------------------------------------------------------

def send_motor_alert(ser, duration_ms: int = 500) -> None:
    """
    Send a vibration alert command to the ESP32 motor driver over serial.

    Only transmits if MOTOR_ENABLED is True and a serial port is open.

    Args:
        ser:         Open serial.Serial instance (or None).
        duration_ms: Duration of vibration in milliseconds (informational only;
                     the ESP32 firmware interprets the 'V' command independently).
    """
    if not MOTOR_ENABLED:
        return
    if ser is None:
        logger.warning("send_motor_alert: no serial connection — alert suppressed.")
        return
    try:
        ser.write(b"V\n")
        logger.info("Motor alert sent (requested %d ms).", duration_ms)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send motor alert: %s", exc)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_reader() -> Union[SyntheticSensorReader, RealSensorReader]:
    """
    Instantiate and return the appropriate sensor reader based on the SYNTHETIC flag.

    Returns:
        SyntheticSensorReader if SYNTHETIC is True, otherwise RealSensorReader.
    """
    if SYNTHETIC:
        logger.info("Creating SyntheticSensorReader (SYNTHETIC=True).")
        return SyntheticSensorReader()
    else:
        logger.info("Creating RealSensorReader (SYNTHETIC=False).")
        return RealSensorReader()


# ---------------------------------------------------------------------------
# Module self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    reader = create_reader()
    tracker = BaselineTracker()

    print("Running sensor reader self-test (5 seconds) …")

    def _print_sample(s: Dict[str, float]) -> None:
        delta = tracker.get_delta(s)
        tracker.update(s)
        print(
            f"t={s['t']:6.2f}s  "
            f"c={s['c']:.0f}  th={s['th']:.0f}  l={s['l']:.0f}  tlj={s['tlj']:.0f}  "
            f"Δc={delta.get('c', 0):+.3f}"
        )

    end = time.monotonic() + 5.0
    while time.monotonic() < end:
        sample = reader.get_sample()
        if sample:
            _print_sample(sample)
        time.sleep(SAMPLE_PERIOD_S)

    print("Self-test complete.")
    sys.exit(0)
