"""
sensor_reader.py
-----------------
Connects to the ESP32 over serial, reads the 50Hz JSON stream,
applies a moving average filter per channel, and exposes a generator
that yields smoothed readings for other scripts (calibration, fusion, etc.)

Usage (standalone test):
    python sensor_reader.py

Usage (as a module):
    from sensor_reader import SensorReader
    reader = SensorReader(port="COM6")
    for reading in reader.stream():
        print(reading)   # {"t": ..., "c": ..., "th": ..., "l": ..., "tlj": ...}
"""

import serial
import serial.tools.list_ports
import json
import time
from collections import deque

# ---------- Config ----------
BAUD_RATE = 115200
WINDOW_SIZE = 10          # moving average window (~200ms at 50Hz) — balanced smoothing without much lag
SENSOR_KEYS = ["c", "th", "l", "tlj"]


def auto_detect_port():
    """Try to find a likely ESP32 serial port on Windows (COMx)."""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None
    # Prefer ports with common USB-serial chip descriptions used by ESP32 boards
    for p in ports:
        desc = (p.description or "").lower()
        if "cp210" in desc or "ch340" in desc or "usb-serial" in desc or "silicon labs" in desc:
            return p.device
    # Fallback: just return the first available COM port
    return ports[0].device


class SensorReader:
    def __init__(self, port=None, baud=BAUD_RATE, window_size=WINDOW_SIZE):
        if port is None:
            port = auto_detect_port()
            if port is None:
                raise RuntimeError(
                    "No serial port found. Plug in the ESP32 and check Device Manager "
                    "for its COM port, then pass it explicitly: SensorReader(port='COM3')"
                )
            print(f"[sensor_reader] Auto-detected port: {port}")

        self.ser = serial.Serial(port, baud, timeout=1)
        time.sleep(2)  # allow ESP32 to reset after serial connection opens
        self.ser.reset_input_buffer()

        self.window_size = window_size
        self.buffers = {k: deque(maxlen=window_size) for k in SENSOR_KEYS}

    def _smooth(self, key, value):
        self.buffers[key].append(value)
        return sum(self.buffers[key]) / len(self.buffers[key])

    def read_raw(self):
        """Read one raw JSON packet from serial. Returns dict or None if invalid/incomplete."""
        try:
            line = self.ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                return None
            data = json.loads(line)
            return data
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def stream(self):
        """Generator yielding smoothed sensor readings, one per valid packet received."""
        while True:
            raw = self.read_raw()
            if raw is None:
                continue
            if not all(k in raw for k in SENSOR_KEYS):
                continue  # skip malformed/partial packets

            smoothed = {"t": raw.get("t")}
            for k in SENSOR_KEYS:
                smoothed[k] = self._smooth(k, raw[k])
            yield smoothed

    def send_alert(self):
        """Send the 'V' trigger byte to fire the vibration motor."""
        self.ser.write(b"V")

    def close(self):
        self.ser.close()


if __name__ == "__main__":
    # Standalone test: print smoothed readings live
    reader = SensorReader()  # auto-detects COM port
    print("Reading smoothed sensor values (Ctrl+C to stop)...")
    try:
        for reading in reader.stream():
            print(reading)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        reader.close()
