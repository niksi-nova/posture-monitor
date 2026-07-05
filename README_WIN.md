# PostureGuard

**Real-time dual-input posture monitoring system**  
_RV College of Engineering — AIML Elective Project_

---

## Overview

PostureGuard is a posture monitoring system that fuses two independent input streams — a live webcam analysed with MediaPipe Pose, and a wearable flex-sensor array on an ESP32 microcontroller — to classify your posture in real time and alert you when you've been slouching.

The system is designed **hardware-optional**: while the physical shirt and ESP32 are being built, the entire software stack runs using a realistic synthetic sensor simulator. Switching to real hardware later requires changing a single flag (`SYNTHETIC = False`) in one file.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Frontend (Vite + React)             │
│  PostureDisplay · SensorPanel · VisionPanel · FusionGauge│
│  CalibrationModal · TrainingPanel · SessionLog           │
└────────────────────┬────────────────────────────────────┘
                     │ WebSocket (15Hz broadcast)
                     │ REST API
┌────────────────────▼────────────────────────────────────┐
│                   FastAPI Backend  (app.py)              │
│                                                          │
│  ┌─────────────────────┐  ┌──────────────────────────┐  │
│  │  Vision Pipeline    │  │  Sensor Reader           │  │
│  │  (MediaPipe Pose)   │  │  (Synthetic or Serial)   │  │
│  │  vision_pipeline.py │  │  sensor_reader.py        │  │
│  └──────────┬──────────┘  └───────────┬──────────────┘  │
│             │  4 ratio features        │  4 ADC deltas    │
│             │  15-frame LSTM window    │  SVM/MLP predict │
│             ▼                          ▼                  │
│  ┌──────────────────────────────────────────────────┐   │
│  │           Fusion Engine  (fusion.py)              │   │
│  │   Quality-weighted late fusion of probabilities   │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
         │                        │
┌────────▼──────────┐   ┌─────────▼──────────┐
│   Vision LSTM     │   │  Sensor SVM/MLP     │
│  (vision_lstm.pt) │   │  (sensor_model.pkl) │
└───────────────────┘   └────────────────────┘
```

---

## Quick Start

### 1. Clone / open the project

```
cd posture-monitor
```

### 2. One-time setup (Windows)

```bat
setup.bat
```

This creates a Python 3.12 venv, installs all Python dependencies, and installs frontend Node packages. Takes ~3–5 minutes on first run.

### 3. Launch everything (Windows)

```bat
start.bat
```

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`

> **macOS / Linux**: use `./setup.sh` and `./start.sh` instead (require `chmod +x` first).

### 4. First-time workflow

1. Browser opens → **Calibration Modal** appears automatically
2. Click **"Begin Calibration"** → hold upright posture for 10 seconds
3. After calibration: click **"Training"** → **"Generate Synthetic Data"** → **"Train Models"**
4. Training completes (~30–60s) → accuracy displayed
5. Live dashboard with animated posture display is now active

---

## Directory Structure

```
posture_monitor/
├── venv/                          Python virtual environment
│
├── backend/
│   ├── pipeline/
│   │   ├── vision_pipeline.py     MediaPipe webcam → 4 ratio features + 15-frame window
│   │   ├── sensor_reader.py       Synthetic simulator OR real ESP32 serial reader
│   │   ├── calibration.py         10s upright calibration → baseline.json
│   │   └── fusion.py              Quality-weighted late fusion engine
│   │
│   ├── training/
│   │   ├── collect_data.py        Labeled session recorder (live or synthetic)
│   │   ├── train_sensor.py        SVM/MLP training on sensor delta features
│   │   ├── train_vision.py        2-layer LSTM training on 15-frame vision windows
│   │   └── evaluate.py            Side-by-side model evaluation report
│   │
│   ├── models/
│   │   ├── sensor_model.pkl       Best sensor classifier (SVM or MLP)
│   │   ├── sensor_scaler.pkl      StandardScaler for sensor features
│   │   ├── vision_lstm.pt         Trained PostureLSTM checkpoint
│   │   ├── sensor_metrics.json    Last training accuracy/F1 for sensor model
│   │   └── vision_metrics.json    Last training accuracy/F1 for vision model
│   │
│   ├── data/
│   │   ├── raw/                   Labeled CSV sessions ({label}_{session_id}.csv)
│   │   ├── processed/             Windowed numpy arrays (created by training scripts)
│   │   └── baseline.json          Per-user calibration baseline
│   │
│   ├── app.py                     FastAPI server — REST + WebSocket
│   └── requirements.txt           Python dependencies
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                Main layout and state management
│   │   ├── index.css              Design system (tokens, base styles, animations)
│   │   ├── main.jsx               React entry point
│   │   ├── hooks/
│   │   │   └── useWebSocket.js    Auto-reconnecting WebSocket hook
│   │   └── components/
│   │       ├── PostureDisplay.jsx  Animated SVG silhouette — hero component
│   │       ├── SensorPanel.jsx     4 bidirectional sensor delta bars
│   │       ├── VisionPanel.jsx     4 circular vision feature gauges
│   │       ├── FusionGauge.jsx     Arc confidence gauge + weight split bar
│   │       ├── CalibrationModal.jsx Countdown ring calibration UI
│   │       ├── TrainingPanel.jsx   Data collection + training trigger
│   │       └── SessionLog.jsx      Scrolling alert history feed
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── setup.sh                       One-time setup script
├── start.sh                       Launch both servers
├── INSTRUCTIONS.md                Hardware integration guide
└── README.md                      This file
```

---

## Backend Deep Dive

### Sensor Reader (`sensor_reader.py`)

**Synthetic mode** (default while hardware isn't ready) simulates the ESP32's 12-bit ADC output at 15Hz with three posture states:

| State        | Cervical (C) | Thoracic (Th) | Lumbar (L) | TLJ       |
| ------------ | ------------ | ------------- | ---------- | --------- |
| Good posture | 2100–2400    | 2100–2400     | 2100–2400  | 2100–2400 |
| Slouch       | ~baseline    | 1700–1900     | 1500–1700  | 1500–1700 |
| Forward head | 1400–1600    | 1800–2000     | ~baseline  | ~baseline |

The simulator:

- Transitions between states via linear interpolation over 2–4 seconds (mimics natural drift)
- Adds a slow drift sine wave (period 120s, amplitude ±80 ADC counts)
- Applies a 5-sample moving average per channel (matching firmware behaviour)
- Runs EMA baseline correction (α=0.0005) for long-session stability

**Real mode** (`SYNTHETIC = False`): Reads JSON from the configured serial port, parses identically, same output contract. See `INSTRUCTIONS.md` for setup.

**Output JSON** (15Hz, matches ESP32 firmware exactly):

```json
{ "t": 1718203451234, "c": 2140, "th": 1820, "l": 3100, "tlj": 2890 }
```

### Vision Pipeline (`vision_pipeline.py`)

Runs MediaPipe Pose in a background thread at 30fps. Extracts 7 landmarks and computes 4 **scale-invariant ratio features** (all divided by shoulder width):

| Feature          | Formula                                                  | Meaning                    |
| ---------------- | -------------------------------------------------------- | -------------------------- |
| `fwd_head_ratio` | `dist(nose, shoulder_midpoint) / shoulder_width`         | Forward head protrusion    |
| `shoulder_tilt`  | `abs(sh_L.y - sh_R.y) / shoulder_width`                  | Lateral shoulder imbalance |
| `torso_lean`     | `dist(hip_midpoint, shoulder_midpoint) / shoulder_width` | Torso inclination          |
| `ear_sh_ratio`   | `dist(ear_midpoint, shoulder_midpoint) / shoulder_width` | Head-shoulder offset       |

A 15-frame sliding window (deque) is maintained thread-safely. If the webcam is unavailable, the system degrades gracefully — vision quality drops to 0 and the fusion engine weights sensor data at 100%.

### Calibration (`calibration.py`)

Collects 10 seconds (150 sensor samples + up to 300 vision frames) of upright posture data, averages each channel, and saves to `backend/data/baseline.json`. All subsequent sensor readings are expressed as normalized deltas against this baseline:

```
delta[sensor] = (live_ADC - baseline_ADC) / baseline_ADC
```

Negative delta = more bent than calibration = bad posture. Values typically range from -0.35 (severe slouch) to +0.05.

### Fusion Engine (`fusion.py`)

Quality-weighted late fusion of both models' probability vectors:

```
q_vision = MediaPipe visibility score (0–1)
q_sensor = clip(1 - std(delta_vector) × 5, 0.1, 1.0)

w_vision = q_vision / (q_vision + q_sensor)
w_sensor = q_sensor / (q_vision + q_sensor)

p_fused = w_vision × p_vision + w_sensor × p_sensor
```

Alert fires when:

- `argmax(p_fused) ≠ "good"` **AND**
- `confidence > threshold` (default 0.7) **AND**
- More than 30 seconds since last alert (cooldown)

---

## Machine Learning Models

### Sensor Model (SVM / MLP)

- **Input**: 4 normalized delta features per sample (flat vector, no windowing)
- **Session-split train/test**: 80% sessions for training, 20% held out
- **Both tried**: SVM (RBF kernel, C=10) and MLP (64→32 hidden layers, ReLU)
- **Best model saved** to `models/sensor_model.pkl`
- **Expected accuracy**: 78–85% on held-out sessions

Training command:

```bash
source venv/bin/activate && cd backend
python training/train_sensor.py
```

### Vision LSTM

- **Architecture**: 2-layer LSTM (hidden=64, dropout=0.3) → Linear(64→32) → ReLU → Dropout → Linear(32→3)
- **Input**: 15-frame sliding window of 4 vision features, shape `(15, 4)`
- **Training**: Adam (lr=1e-3, weight_decay=1e-4), 50 epochs, ReduceLROnPlateau
- **Expected accuracy**: 80–88% on held-out sessions

Training command:

```bash
source venv/bin/activate && cd backend
python training/train_vision.py
```

### Generating Synthetic Training Data (No Hardware Needed)

```bash
source venv/bin/activate && cd backend
python training/collect_data.py --generate-synthetic
```

This generates **6 sessions per label** (18 CSVs total, ~18 minutes of simulated data) using the same synthetic engine as the real-time simulator. Training runs immediately after.

---

## Frontend

The UI uses a **wellness journal aesthetic** — warm cream backgrounds, serif Playfair Display headings, muted purples and greens, paper-texture feel. No dark mode. No harsh borders.

### Key Components

**PostureDisplay** — The hero: an animated SVG silhouette that morphs between upright, slouched, and forward-head shapes using CSS path transitions. Large status text in Playfair Display. Pulsing alert ring when posture is bad.

**SensorPanel** — 4 bidirectional bars, one per sensor. Bar fills left (compressed = bad) or right (extended = OK) from a center zero point. Raw ADC in JetBrains Mono below each bar.

**VisionPanel** — 4 circular SVG arc gauges for vision features. Reference line marks the calibrated value. Green when near reference, purple when deviating.

**FusionGauge** — Semicircle arc gauge showing fused confidence. Below: a split bar showing the current vision vs. sensor weight ratio. Probability mini-table for all three classes.

**CalibrationModal** — Countdown SVG ring (10s). Auto-opens if no calibration found on startup.

**TrainingPanel** — Collapsible panel. One-click synthetic data generation + model training. Shows accuracy for both models after training completes.

**SessionLog** — Last 20 alerts in a scrolling feed. Each entry: timestamp, posture, confidence, duration.

### WebSocket Data

The frontend connects to `ws://localhost:8000/ws` and receives updates at ~15Hz:

```json
{
  "timestamp": 1718203451234,
  "posture": "slouch",
  "confidence": 0.87,
  "alert": true,
  "sensor": { "raw": {...}, "delta": {...}, "quality": 0.82 },
  "vision": { "features": {...}, "visibility": 0.91, "quality": 0.91 },
  "fusion": { "weights": {...}, "probabilities": {...} }
}
```

The `useWebSocket` hook reconnects automatically with exponential backoff (500ms → 5s) and measures ping-pong latency.

---

## API Reference

| Method | Endpoint                | Description                                          |
| ------ | ----------------------- | ---------------------------------------------------- |
| `GET`  | `/health`               | Health check — uptime, timestamp                     |
| `GET`  | `/status`               | System state — calibrated, models loaded, mode       |
| `POST` | `/calibrate`            | Start 10s calibration session                        |
| `POST` | `/train?synthetic=true` | Generate synthetic data + train both models          |
| `POST` | `/train`                | Train on real collected data                         |
| `POST` | `/alert-threshold`      | Body: `{"threshold": 0.8}` — update fusion threshold |
| `WS`   | `/ws`                   | Real-time data stream at 15Hz                        |

Interactive Swagger docs at `http://localhost:8000/docs`.

---

## Hardware Integration (Summary)

When the ESP32 + flex sensor shirt is ready:

1. Flash firmware (outputs `{"t":..,"c":..,"th":..,"l":..,"tlj":..}` at 115200 baud, 15Hz)
2. In `backend/pipeline/sensor_reader.py`: set `SYNTHETIC = False`, `SERIAL_PORT = "/dev/ttyUSB0"`
3. Run calibration with shirt on
4. Collect 2 real sessions per posture label per team member (18 CSVs)
5. Retrain both models
6. Set `MOTOR_ENABLED = True` to enable vibration alerts

**Full instructions**: see [`INSTRUCTIONS.md`](INSTRUCTIONS.md)

---

## Requirements

### Python (backend)

- Python 3.10+
- fastapi, uvicorn, websockets
- mediapipe ≥ 0.10
- opencv-python
- torch (CPU)
- scikit-learn
- numpy, pandas, matplotlib, joblib
- pyserial (for real hardware)

### Node (frontend)

- Node.js 18+
- React 18, Vite 5, @vitejs/plugin-react

---

## Team

| Name            | Role                                     |
| --------------- | ---------------------------------------- |
| (Team Member 1) | Hardware — ESP32 firmware, sensor wiring |
| (Team Member 2) | ML — model training, feature engineering |
| (Team Member 3) | Software — backend pipeline, frontend    |

**Institution**: RV College of Engineering  
**Course**: AIML Elective  
**Academic Year**: 2024–25

---

## License

This project is for academic purposes at RV College of Engineering.

---

## Troubleshooting

| Symptom                  | Fix                                                                                                                         |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| `ModuleNotFoundError`    | Activate venv first: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (macOS/Linux)                          |
| Port 8000 in use         | `for /f "tokens=5" %a in ('netstat -aon ^                                                                                   | find ":8000"') do taskkill /PID %a /F` |
| Port 5173 in use         | Same as above, replace `8000` with `5173`                                                                                   |
| Camera not found         | Check `CAMERA_INDEX = 0` in `vision_pipeline.py`, try `1`                                                                   |
| Training fails (no data) | Run "Generate Synthetic Data" first                                                                                         |
| WebSocket disconnected   | Check backend is running; hard refresh browser                                                                              |
| MediaPipe import error   | `pip install mediapipe --upgrade` inside venv                                                                               |
| `torch` not found        | `pip install torch` inside venv (CPU build, ~200MB)                                                                         |
| Serial port not found    | Open Device Manager → Ports (COM & LPT) — find your ESP32 port; update `SERIAL_PORT` in `backend/pipeline/sensor_reader.py` |

---

## Software Development Notes (July 4th)

During software testing before physical hardware integration, several overrides were implemented:

1. **Synthetic Sensor is locked to 'Good' Posture**: (`backend/pipeline/sensor_reader.py`) This prevents the simulated sensor data from injecting "slouching" states while you test your live webcam. Once you plug in the ESP32, change `SYNTHETIC = False`.
2. **Webcam Visibility Metric**: The MediaPipe vision pipeline now only checks visibility of your nose and shoulders, ignoring the hips (which are rarely visible on desktop webcams).
3. **Dynamic Calibration Shifting**: The Vision AI Model mathematically offsets your real-time webcam data upon Calibration to match the AI's expected baseline. **You do not need to retrain the AI models just to test it!**
4. **Faster Alert Testing**: (`backend/pipeline/fusion.py`) `ALERT_COOLDOWN_S` was lowered from `30.0` to `3.0` seconds so you can trigger multiple alerts rapidly.
5. **How to Retrain**: Open the Web UI, expand the **Training** panel, click **Start Recording**, intentionally sit in Good/Slouching/Forward-Head postures as instructed by the UI, then hit the train buttons to generate new `.pt` and `.pkl` models!
