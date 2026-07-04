# Hardware Integration Guide — PostureGuard ESP32

> **Status**: This guide is for when you are ready to connect the physical hardware (flex sensors + ESP32 + vibration motor). The software currently runs entirely in synthetic simulation mode. When you follow this guide, you swap simulation for real hardware by changing a single flag.

---

## Prerequisites

Before following this guide, ensure:
- The PostureGuard software stack is installed and working (`./setup.sh` ran clean)
- You have successfully trained models on synthetic data and verified the dashboard works
- Your ESP32 is flashed with the correct firmware (see Step 1)
- You have the compression shirt with 4 flex sensors sewn in

---

## Step 1 — Flash the ESP32 Firmware

The firmware file is specified in the project PRD (`firmware/esp32_sensor.ino`). This file is **not included** in the software repository — it is the hardware team's deliverable.

The firmware **must** output JSON over USB serial at **115200 baud, 50Hz**, in exactly this format:

```json
{"t": 1718203451234, "c": 2140, "th": 1820, "l": 3100, "tlj": 2890}
```

| Field | Description | GPIO Pin | Flex Sensor Location |
|-------|-------------|----------|----------------------|
| `t`   | Unix timestamp in milliseconds | — | — |
| `c`   | Cervical (neck) ADC value, 12-bit (0–4095) | GPIO 32 | Back of neck (C5–C7) |
| `th`  | Thoracic ADC value | GPIO 33 | Upper back (T4–T6) |
| `l`   | Lumbar ADC value | GPIO 34 | Lower back (L3–L5) |
| `tlj` | Thoracolumbar junction ADC value | GPIO 35 | Mid-back junction |

**Vibration motor**: connected to GPIO 27 (active HIGH). The firmware should activate it when it receives `'V\n'` over serial from the backend (when `MOTOR_ENABLED = True`).

**Verify firmware is working**: Open Arduino Serial Monitor at 115200 baud. You should see a new JSON line every ~20ms (50Hz). The values should be stable in the 1800–2400 range when sitting upright.

---

## Step 2 — Switch Off Synthetic Mode

Open `backend/pipeline/sensor_reader.py`. Near the top of the file, find the constants block (around line 10–20):

```python
# ──── CHANGE THESE THREE LINES ─────────────────────────────────────────────
SYNTHETIC = False          # ← was True — set to False for real hardware
SERIAL_PORT = "/dev/ttyUSB0"   # ← macOS/Linux: find with `ls /dev/tty*`
                               #   Windows: use "COM3" (check Device Manager)
BAUD_RATE = 115200         # ← must match firmware
# ───────────────────────────────────────────────────────────────────────────
```

**Finding your serial port**:
- **macOS**: `ls /dev/tty.usbserial-*` or `ls /dev/tty.SLAB_USBtoUART`
- **Linux**: `ls /dev/ttyUSB*` or `ls /dev/ttyACM*`
- **Windows**: Open Device Manager → Ports (COM & LPT) → look for "Silicon Labs CP210x" or "CH340"

**Test serial connection before starting the app**:
```bash
source venv/bin/activate
python3 -c "
import serial, time
ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
for _ in range(5):
    line = ser.readline()
    print(line.decode().strip())
"
```

You should see 5 JSON lines. If you see garbage bytes, check baud rate. If you see nothing, check the port name.

---

## Step 3 — Run Calibration With the Real Shirt

> **Important**: This step overwrites `backend/data/baseline.json` with real hardware values. Do this every time you start a new session or change who is wearing the shirt.

1. Put on the compression shirt. Make sure all 4 sensor connections are secure.
2. Start the PostureGuard app: `./start.sh`
3. Open `http://localhost:5173`
4. The Calibration Modal will appear automatically on first load.
5. **Sit upright**: spine neutral, shoulders back, look straight ahead at the screen.
6. Click **"Begin Calibration"** and hold the position for 10 seconds.
7. The baseline is saved. The modal dismisses.

**Alternative**: POST to the API directly:
```bash
curl -X POST http://localhost:8000/calibrate
```

The saved `baseline.json` will look like:
```json
{
  "cervical": 2187,
  "thoracic": 2043,
  "lumbar": 2311,
  "tlj": 2244,
  "calibrated_at": "2024-06-15T10:30:00",
  "vision_reference": [1.19, 0.021, 1.83, 0.88]
}
```

Real hardware values will differ from the synthetic defaults. This is expected — the baseline is what matters, not the absolute ADC values.

---

## Step 4 — Collect Real Training Data

Synthetic training data gives you a working demo, but real data from your actual sensors will give dramatically better accuracy. Aim for **2 sessions per label per team member** (18 CSVs total).

**Using the UI** (recommended):
1. In the dashboard, click **"Training"** to expand the TrainingPanel.
2. Select a label from the dropdown: Good / Slouch / Forward Head.
3. Click **"Start Recording"**.
4. Perform the posture genuinely for **60 seconds** while wearing the shirt.
5. The session CSV is saved to `backend/data/raw/`.
6. Repeat for all 3 labels, all 3 team members.

**Tip for good data quality**:
- **Good posture**: Sit the way you would if someone told you to sit up straight. Don't over-arch.
- **Slouch**: Let your spine curve naturally — don't exaggerate. Shoulders roll forward.
- **Forward head**: Keep your spine relatively straight but push your head forward toward the screen. Think "reading glasses posture."

**Using the CLI** (for automation):
```bash
source venv/bin/activate
cd backend
python training/collect_data.py --label good --session-id person1_session1
python training/collect_data.py --label slouch --session-id person1_session2
python training/collect_data.py --label forward_head --session-id person1_session3
```

---

## Step 5 — Retrain Models on Real Data

After collecting real training data:

1. In the TrainingPanel, click **"Train Models"** (without the synthetic checkbox).
2. Training takes ~2–3 minutes for both models.
3. The panel shows live accuracy metrics when done.

**Or via CLI**:
```bash
source venv/bin/activate
cd backend
python training/train_sensor.py
python training/train_vision.py
```

**Expected accuracy on real data**: Slightly lower than synthetic (78–82% vs 80–88%) because real sensors have more noise. This is normal. If accuracy is below 70%, check your data collection — ensure each label session is genuinely different postures.

---

## Step 6 — Enable Motor Alerts

Once the system is performing well, enable the vibration motor feedback:

In `backend/pipeline/sensor_reader.py`:
```python
MOTOR_ENABLED = True   # ← was False
```

When `alert=True` in the fusion output, the backend sends `'V\n'` over the same serial connection to GPIO 27, which triggers a 500ms vibration burst.

**Testing**: Intentionally slouch. The SessionLog should show an alert within ~1 second, and the motor should vibrate.

---

## Step 7 — Verify End-to-End

Run through this checklist after switching to real hardware:

| Test | Expected Result |
|------|-----------------|
| Sit upright | Sensor bars near center (0% delta), posture = "Good" |
| Slouch deliberately | L and TLJ bars go negative (red), posture = "Slouch" within 2s |
| Forward head | C bar goes most negative, posture = "Forward Head" within 2s |
| Block webcam | Vision quality drops, system relies more on sensors |
| Disconnect USB | RealSensorReader retries with backoff, logs error, reconnects |
| Alert fires | Motor vibrates 500ms, SessionLog entry appears |
| Re-alert cooldown | Second alert suppressed for 30s after first |

---

## Troubleshooting

### ADC values stuck at 0 or 4095
- **Cause**: Open circuit (0) or short circuit (4095) in voltage divider
- **Fix**: Check flex sensor solder joints. Check 47kΩ resistor connections. Verify 3.3V rail is active (measure with multimeter).

### Sensor values drift significantly over a long session
- **Cause**: Temperature change affecting flex sensor resistance, or natural position drift
- **Fix**: Run recalibration every 30 minutes. Alternatively, reduce EMA alpha:
  ```python
  EMA_ALPHA = 0.0003   # Slower adaptation (was 0.0005)
  ```

### Vision quality consistently low (< 0.5)
- **Cause**: Poor lighting, sitting too far from camera, camera partially blocked
- **Fix**: Ensure front-facing light source. Sit 60–90cm from camera. Check MediaPipe confidence thresholds in `vision_pipeline.py`.

### High false positive rate (alerts when sitting fine)
- **Cause**: Alert threshold too low, or models trained on unrepresentative data
- **Fix**: Raise threshold in UI (default 0.7 → try 0.85). Or re-collect training data for the "good" class with more variation.

### Motor not vibrating
- **Fix**: Verify `MOTOR_ENABLED = True`. Check GPIO 27 wiring. Ensure backend is running with the same serial port as the sensor reader (not a separate connection).

### Serial port "Permission denied" on Linux
```bash
sudo usermod -aG dialout $USER
# Log out and back in for group change to take effect
```

### ImportError or ModuleNotFoundError on startup
- Make sure you're running from within the virtual environment:
  ```bash
  source venv/bin/activate
  cd backend
  uvicorn app:app --reload --port 8000
  ```

---

## Quick Reference: What Changes vs. What Stays the Same

| What changes | File | Line |
|--------------|------|------|
| `SYNTHETIC = False` | `pipeline/sensor_reader.py` | ~10 |
| `SERIAL_PORT = "..."` | `pipeline/sensor_reader.py` | ~12 |
| `MOTOR_ENABLED = True` | `pipeline/sensor_reader.py` | ~17 |
| Run real calibration | UI or `POST /calibrate` | — |
| Collect real training data | UI or CLI | — |
| Retrain models | UI or CLI | — |

**Everything else — the entire pipeline, frontend, FastAPI server, fusion engine — remains identical.**

---

*PostureGuard — RV College of Engineering AIML Project*  
*Hardware Integration Guide v1.0*

---

## Important Software Updates (July 4th)
Several backend logic adjustments were made to ensure the UI and ML models run reliably during testing before the real hardware is connected:

1. **Synthetic Sensor is locked to 'Good' Posture**: 
   In `backend/pipeline/sensor_reader.py`, `STATE_SEQUENCE` is locked to `["good"]`. This is so the simulated sensor data doesn't randomly inject "slouching" states while you try to test your physical live webcam. Once you plug in the ESP32, change `SYNTHETIC = False` and this lock will be ignored.
   
2. **Webcam Visibility Metric**: 
   The MediaPipe vision pipeline now only checks visibility of your nose and shoulders. We removed the "hip visibility" requirement, as a desktop webcam rarely sees your hips.

3. **Dynamic Calibration Shifting**: 
   The Vision AI Model was trained on synthetic data expecting a perfect mathematical posture ratio. Your natural posture on webcam will be slightly different. When you click **Recalibrate** in the UI, the backend will now mathematically offset your real-time webcam data to match the AI's expected baseline. **You do not need to retrain the AI models just to test it!**
   
4. **Faster Alert Testing**:
   In `backend/pipeline/fusion.py`, `ALERT_COOLDOWN_S` was lowered from `30.0` to `3.0` seconds so you can trigger multiple alerts rapidly in the UI while testing.

5. **Retraining (Optional)**:
   If you DO want to retrain on real data: open the Web UI, expand the **Training** panel, click **Start Recording**, intentionally sit in Good/Slouching/Forward-Head postures as instructed by the UI, then hit the train buttons to generate new `.pt` and `.pkl` models!
