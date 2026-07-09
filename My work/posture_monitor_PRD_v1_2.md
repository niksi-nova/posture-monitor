# Product Requirements Document
# Intelligent Ergonomic Health Monitoring System
## Hybrid Posture Monitoring & Correction System

**Course:** Artificial Intelligence and Machine Learning (AI244AI)
**Team:** Anika U Bhat (1RV24CI016) · Anushka Sharan Basappa R (1RV24CI020) · Atul Roshan Naik (1RV24CI025)
**Department:** AIML, RV College of Engineering
**Document version:** 1.3 (updated — Phases 1–5 complete, Phase 6 in progress)
**SDG Alignment:** SDG 3 — Good Health & Well-being
**Last updated:** 2026-07-09

---

## 1. Project Overview

### 1.1 Problem Statement

Prolonged poor posture among students and office workers causes chronic musculoskeletal disorders. Existing single-input correctors (sensor-only or camera-only) fail under real-world conditions:

- **Sensor-only** systems drift over time due to heat and mechanical memory in flex sensors
- **Camera-only** systems fail in low light or when the user turns away from the webcam
- Neither approach eliminates false positives reliably on its own

**Target users:** College students, software professionals, and remote workers spending 6–10 hours daily at a desk.

**Our solution:** A dual-input, sensor-fusion system that cross-references physical spinal curvature data (4 flex sensors + ESP32) with AI-based visual skeletal tracking (MediaPipe Pose + webcam) for highly accurate, real-time haptic correction feedback. The full software stack now runs **hardware-optional** — while the physical shirt/ESP32 is being finalised, all pipelines operate using a realistic synthetic sensor simulator (`SYNTHETIC = True` in `sensor_reader.py`). Switching to real hardware requires changing one flag.

### 1.2 Core Value Proposition

- Eliminates false positives through redundant signal sources
- Non-intrusive: no user action required once calibrated
- Real-time: haptic feedback latency target < 1 second from slouch onset
- Wearable: compression shirt form factor, no desktop-only dependency
- **Hardware-optional**: full demo runs with synthetic sensor data while hardware is being built

---

## 2. Hardware Specification

### 2.1 Component List

| Component | Spec | Qty | Purpose |
|---|---|---|---|
| Flex sensor 2.2" | Spectra Symbol, ~25–80kΩ range | 4 (all same size) | Cervical, thoracic, thoracolumbar junction, lumbar sensing |
| ESP32 DevKit V1 | 12-bit ADC, BT/Wi-Fi, 3.3V logic | 1 | Microcontroller, ADC, BT streaming |
| Fixed resistors 47kΩ | 1/4W | 4 | Voltage divider (one per sensor) |
| 2N2222 NPN transistor | TO-92 package | 1 | Motor driver switch |
| 1N4001 diode | 1A rectifier | 1 | Flyback protection for motor |
| 1kΩ resistor | 1/4W | 1 | Base resistor for 2N2222 |
| 100nF ceramic capacitor | 50V | 1 | Motor EMI suppression |
| Coin vibration motor | 3V, ~70mA | 1 | Haptic alert feedback |
| LiPo battery | 3.7V, 500mAh+ | 1 | Portable power supply |
| TP4056 module | USB-C charging, protection | 1 | LiPo charger + protection |
| SPDT slide switch | Any panel mount | 1 | Power on/off |
| Compression shirt | Fitted, center back seam | 1 | Sensor mounting platform |
| Breadboard | Full-size | 1 | Circuit integration — **final build platform (perfboard step skipped by team decision)** |
| Female pin headers | 2×19 | 2 | ESP32 socket (removable) |
| 1080p Webcam | USB, 30fps | 1 | Vision input |

**Note:** The team decided to skip transferring the circuit to perfboard and keep the final build on breadboard. This is acceptable for a course project scope but carries a higher risk of wires loosening during wear — worth monitoring if ADC readings become intermittent later.

### 2.2 Sensor Placement

Sensors are mounted vertically along the center back seam of the compression shirt, on the skin-facing side, in sewn fabric channels:

```
Position    Sensor    Vertebral level    ESP32 pin
S1          2.2"      C5–C7 (neck base)  GPIO 32
S2          2.2"      T1–T8 (mid-upper)  GPIO 33
S3          2.2"      T12–L1 (junction)  GPIO 34
S4          2.2"      L1–L4 (lumbar)     GPIO 35
```

All sensors are identical 2.2" size. Resistance ranges are uniform across all 4 channels (~25–35kΩ flat, 70–100kΩ bent).

Leave 3mm gaps between sensors. Route wires along the seam in a fabric sleeve to a waist pocket holding the breadboard + ESP32. Vibration motor mounts on the front chest (sternum area) for clear haptic feedback.

### 2.3 Voltage Divider Circuit (×4) — CONFIRMED WORKING

One per sensor, shared 3.3V and GND rails:

```
3.3V ──── [Flex sensor ~30–80kΩ] ──── ADC pin (GPIO 32–35)
                                  |
                               [47kΩ fixed]
                                  |
                                GND
```

- Flat sensor (~30kΩ): V_out ≈ 2.01V → ADC ≈ 2498
- Bent sensor (~80kΩ): V_out ≈ 1.22V → ADC ≈ 1514
- Usable range: ~1000 ADC counts per sensor — sufficient resolution
- **Build status: COMPLETE.** All 4 dividers built and verified on breadboard. Live-tested with full firmware — bending a sensor produces a clean, isolated response (e.g. S1 dropped from ~2080 resting to ~1170 fully bent) while the other 3 channels stayed flat.

**Why 47kΩ (not 10kΩ):** The midpoint of the flex sensor's resistance range is ~50kΩ. A 47kΩ fixed resistor maximizes voltage swing sensitivity in the working range. A 10kΩ divider compresses the signal into the low end of the ADC range.

### 2.4 Motor Driver Circuit

```
3.3V ──────────────────── Motor (+)
                          Motor (–) ──── 2N2222 Collector
1N4001 across motor terminals (cathode toward 3.3V)
100nF ceramic cap across motor terminals
GPIO27 ──── 1kΩ ──── 2N2222 Base
2N2222 Emitter ──── GND
```

GPIO HIGH → transistor conducts → motor spins.
Flyback diode clamps reverse EMF when motor is switched off.
100nF cap suppresses switching noise that would corrupt ADC readings.

**Why the transistor circuit is needed:** A GPIO pin can safely source only ~12–20mA, while the motor draws ~70mA — directly driving it from a pin risks damaging the ESP32. The transistor switches higher current from the 3.3V rail using a small GPIO-controlled base current. The diode protects against back-EMF spikes from the motor's inductive coil. The 100nF cap is specifically needed because ADC-sensitive sensor lines run on the same board.

**Build status: COMPLETE.** Motor buzzes cleanly on GPIO27 HIGH via serial 'V' command. No ADC channel jumped more than ±20 counts during motor firing — confirmed with sensors and motor running simultaneously.

### 2.5 Power Architecture

```
USB-C → TP4056 → LiPo (3.7V)
LiPo → SPDT switch → ESP32 VIN pin (onboard 3.3V LDO regulates to 3.3V)
```

Never connect LiPo directly to the ESP32 3V3 pin — bypasses regulation.
During development, power via USB only (no LiPo needed). LiPo/TP4056 integration is deferred to Phase 6 (wireless operation).

### 2.6 Hardware Build Verification Checklist — ALL COMPLETE

Before powering on (ohmmeter):
- [x] Each flex sensor flat: 25–35kΩ (2.2")
- [x] Each flex sensor fully bent: 70–100kΩ
- [x] 3.3V rail to GND: open circuit (>1MΩ) — no shorts
- [x] 2N2222 B-C and E-C: open (transistor off)

After power on (USB only):
- [x] 3.3V confirmed at power rail with multimeter
- [x] All 4 ADC channels print values ~1800–2100 at rest
- [x] Each sensor's ADC value changes independently on bend
- [x] Motor buzzes on GPIO27 HIGH, no ADC channel jumps >±20 counts
- [x] Confirmed no cap issue — 100nF across motor terminals sufficient

---

## 3. Firmware Specification (ESP32, C++ / Arduino) — COMPLETE

**File:** `firmware/esp32_sensor.ino` — written, flashed, and verified.

### 3.1 ADC Reading

- **Pins:** GPIO 32, 33, 34, 35 (input-only pins, safe for ADC)
- **Hardware averaging:** Read each pin 8× per sample, take integer average — suppresses high-frequency electrical noise at source
- **Output rate:** Fixed 50Hz (one JSON packet every 20ms via `delay(20)` equivalent, non-blocking `millis()` timing used in final code)
- **Resolution:** 12-bit (0–4095)

### 3.2 Output Format

```json
{"t":139224,"c":1170,"th":2081,"l":2284,"tlj":1831}
```

- `t`: milliseconds since ESP32 boot (NOT wall-clock Unix time — see note below)
- `c`: 12-bit ADC reading for cervical sensor (GPIO 32), 8x oversampled average
- `th`: thoracic sensor (GPIO 33)
- `l`: lumbar sensor (GPIO 35)
- `tlj`: thoracolumbar junction sensor (GPIO 34)

**Timestamp note:** The firmware currently emits `millis()` (time since boot), not true Unix time, since the ESP32 has no onboard RTC. For syncing with webcam frame timestamps in Phase 4, `sensor_reader.py` (or a downstream script) should record the PC wall-clock time when the first packet arrives and use it as an offset to convert subsequent `t` values to approximate Unix time.

### 3.3 Motor Control

- Listens for a single byte `'V'` over Serial
- On receipt: sets GPIO27 HIGH for a fixed 300ms pulse, then LOW
- Verified: buzzes reliably, no ADC interference

### 3.4 Verified Behavior (live test log)

```
23:13:52.271 -> {"t":139224,"c":1170,"th":2081,"l":2284,"tlj":1831}
23:13:52.309 -> {"t":139244,"c":1194,"th":2083,"l":2285,"tlj":1830}
23:13:52.309 -> {"t":139264,"c":1221,"th":2082,"l":2284,"tlj":1826}
...
23:13:52.528 -> {"t":139484,"c":1710,"th":2085,"l":2284,"tlj":1825}
```
Cervical channel (`c`) shows a clean, isolated bend response (2080 resting → 1170 fully bent) while `th`, `l`, `tlj` remain stable. Packet timing consistent with ~20ms (50Hz) intervals.

---

## 4. Software Stack & Project Structure

### 4.1 Dependencies

| Library | Version | Purpose |
|---|---|---|
| FastAPI | 0.111.0 | REST API + WebSocket backend server |
| Uvicorn | 0.29.0 | ASGI server for FastAPI |
| MediaPipe | 0.10.14 | Pose landmark extraction (33-landmark model) |
| OpenCV | ≥4.9.0 | Webcam capture |
| PySerial | ≥3.5 | ESP32 serial communication |
| PyTorch | ≥2.2.0 | Vision LSTM training and inference |
| scikit-learn | ≥1.4.0 | Sensor SVM model training and inference |
| NumPy / pandas | ≥1.26 / ≥2.2 | Data handling |
| matplotlib | ≥3.8 | Evaluation plots |
| joblib | ≥1.4 | Model serialisation |
| React + Vite | (frontend) | Real-time dashboard UI |

### 4.2 Install

```bash
# Backend
pip install fastapi==0.111.0 uvicorn[standard]==0.29.0 websockets==12.0 \
    mediapipe==0.10.14 "opencv-python>=4.9.0" "pyserial>=3.5" \
    "torch>=2.2.0" "scikit-learn>=1.4.0" "numpy>=1.26.0" \
    "pandas>=2.2.0" "matplotlib>=3.8.0" "joblib>=1.4.0" \
    "python-multipart>=0.0.9" "httpx>=0.27.0"

# Frontend (from posture-monitor/frontend/)
npm install
npm run dev
```

### 4.3 Project Folder Structure (Current State)

```
posture-monitor/
├── firmware/
│   └── esp32_sensor.ino             # DONE — flashed & verified
├── backend/
│   ├── app.py                       # DONE — FastAPI server (887 lines)
│   ├── requirements.txt             # DONE
│   ├── data/
│   │   ├── baseline.json            # DONE — calibration baseline on disk
│   │   ├── raw/                     # DONE — 6 labeled session CSVs collected
│   │   └── processed/               # (windowed features, auto-generated)
│   ├── models/
│   │   ├── sensor_model.pkl         # DONE — trained SVM classifier (27 KB)
│   │   ├── sensor_scaler.pkl        # DONE — paired StandardScaler (480 B)
│   │   ├── sensor_metrics.json      # DONE — evaluation results
│   │   ├── vision_lstm.pt           # DONE — trained 2-layer LSTM (218 KB)
│   │   └── vision_metrics.json      # DONE — evaluation results
│   ├── pipeline/
│   │   ├── sensor_reader.py         # DONE — synthetic + real serial, EMA drift (597 lines)
│   │   ├── vision_pipeline.py       # DONE — MediaPipe, 15-frame sliding window (448 lines)
│   │   ├── fusion.py                # DONE — quality-weighted late fusion (304 lines)
│   │   └── calibration.py           # DONE — 10s dual-modality calibration (316 lines)
│   └── training/
│       ├── collect_data.py          # DONE — live + synthetic data collection (417 lines)
│       ├── train_sensor.py          # DONE — SVM training script
│       ├── train_vision.py          # DONE — LSTM training script
│       └── evaluate.py              # DONE — model evaluation script
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx                  # DONE — main app, WebSocket integration
│       ├── index.css                # DONE
│       ├── main.jsx
│       ├── components/
│       │   ├── PostureDisplay.jsx   # DONE — live posture state display
│       │   ├── SensorPanel.jsx      # DONE — live sensor ADC readings
│       │   ├── VisionPanel.jsx      # DONE — MediaPipe feature display
│       │   ├── FusionGauge.jsx      # DONE — fused confidence gauge
│       │   ├── CalibrationModal.jsx # DONE — calibration flow UI
│       │   ├── TrainingPanel.jsx    # DONE — trigger training from UI
│       │   └── SessionLog.jsx       # DONE — alert history log
│       └── hooks/                   # Custom React hooks
├── setup.bat / setup.sh             # One-time environment setup scripts
├── start.bat / start.sh             # Start backend + frontend together
└── README.md / README_WIN.md        # Full setup + usage docs
```

---

## 5. Implementation Plan & Progress

### Phase 1 — Hardware & Firmware (Target: Week 1) — ✅ COMPLETE

**Goal:** All 4 sensors reading stable, timestamped ADC values over serial at 50Hz.

- [x] Build one voltage divider on breadboard. Verify ADC readings with multimeter and Serial Monitor.
- [x] Build remaining 3 dividers. Confirm all 4 channels independent.
- [x] Build motor driver. Verify motor fires on GPIO HIGH, no ADC corruption.
- [x] ~~Transfer to perfboard~~ — **Team decision: staying on breadboard for the full build.** Skipped by choice, not blocked.
- [ ] Prepare compression shirt: sew sensor channels, route wiring to waist pocket, mount motor on chest.
- [x] Flash ESP32 with full sensor firmware. Verify 50Hz JSON stream with timestamps via Serial Monitor.

**Exit criteria: MET.** Serial Monitor shows clean JSON at 50Hz. All 4 ADC values change independently when sensors are bent by hand. Motor pulses cleanly on command.

**Remaining Phase 1 item:** Shirt sewing/mounting — can be done in parallel with Phase 2/3 software work since it doesn't block software development.

### Phase 2 — Active Calibration & Sensor Baseline (Target: Week 1–2) — ✅ COMPLETE

**What was built (significantly exceeds original plan):**

- [x] **`pipeline/sensor_reader.py`** (597 lines) — full dual-mode implementation:
  - `SYNTHETIC = True/False` flag to switch between synthetic simulator and real ESP32 serial
  - Synthetic mode: realistic ADC simulation with Gaussian noise, sinusoidal drift, and lerp-based posture transitions
  - Real mode: auto-detects Windows COM port (default `COM6`), parses JSON, applies 5-sample moving average
  - **EMA drift correction implemented:** `EMA_ALPHA = 0.0005` per sample
  - `BaselineTracker` class: tracks per-channel baselines; computes normalized delta vector (live − baseline)
  - `send_alert()` method: sends `'V\n'` byte over serial to trigger motor from Python
  - `POSTURE_TARGETS` dict: defines good/slouch/forward_head ADC target distributions for synthetic data
- [x] **`pipeline/calibration.py`** (316 lines) — dual-modality 10s calibration:
  - Collects simultaneous sensor samples and vision frames during calibration window
  - Computes per-channel means for cervical, thoracic, lumbar
  - Computes 4-element `vision_reference` vector (mean of 4 features during calibration)
  - Saves `baseline.json` with all values + ISO-8601 UTC timestamp
  - `is_calibrated()` / `load_baseline()` convenience helpers
- [x] **`baseline.json`** exists on disk (calibrated 2026-07-06):
  ```json
  {"cervical": 2250.0, "thoracic": 2150.0, "lumbar": 2300.0,
   "calibrated_at": "2026-07-06T14:21:13.471748+00:00",
   "vision_reference": [0.9089, 0.0126, 1.9662, 0.9115]}
  ```

**Exit criteria: MET.** Calibration produces sensible `baseline.json`, delta vector exposed via `BaselineTracker`.

---

### Phase 3 — Vision Pipeline (Target: Week 2) — ✅ COMPLETE

- [x] **`pipeline/vision_pipeline.py`** (448 lines):
  - Background daemon thread captures webcam at `TARGET_FPS = 30`
  - MediaPipe Pose (min_detection_confidence=0.5, min_tracking_confidence=0.5)
  - **Landmark indices used:** 0 (nose), 7 (left ear), 8 (right ear), 11 (left shoulder), 12 (right shoulder), 23 (left hip), 24 (right hip)
  - **4 normalized ratio features per frame (scale-invariant):**
    - `fwd_head_ratio`: forward head distance / shoulder width
    - `shoulder_tilt`: vertical shoulder misalignment / shoulder width
    - `torso_lean`: hip-to-shoulder height / shoulder width
    - `ear_sh_ratio`: ear midpoint to shoulder midpoint / shoulder width
  - `WINDOW_SIZE = 15` frame sliding deque (padded with zeros until full)
  - Thread-safe `get_state()` returns window + `visibility` quality score + `timestamp_ms`
  - `is_camera_available()` check for graceful fallback
  - `get_pipeline()` / `start_pipeline()` module-level API

**Exit criteria: MET.** Runs at 30fps, stable normalized features, visibility drops on occlusion.

---

### Phase 4 — Data Collection & Model Training (Target: Week 3) — ✅ COMPLETE

- [x] **`training/collect_data.py`** (417 lines) — two modes:
  - **Live collection:** logs sensor deltas + vision features + manual label to CSV at 50Hz for 60 seconds
  - **Synthetic generation** (`--generate-synthetic`): creates 6 sessions per class programmatically
  - CSV schema (9 columns): `timestamp, delta_c, delta_th, delta_l, fwd_head_ratio, shoulder_tilt, torso_lean, ear_sh_ratio, label`
- [x] **`training/train_sensor.py`** — SVM with RBF kernel, StandardScaler normalization, session-split evaluation
- [x] **`training/train_vision.py`** — PyTorch 2-layer LSTM, 15-frame windows, early stopping, session-split evaluation
- [x] **`training/evaluate.py`** — evaluation suite for both models
- [x] **6 labeled session CSVs** in `backend/data/raw/`: 2× good, 2× slouch, 2× forward_head
- [x] **Models trained and saved to `backend/models/`:**
  - `sensor_model.pkl` (SVM, 27 KB) + `sensor_scaler.pkl` (480 B)
  - `vision_lstm.pt` (218 KB)

**Model evaluation results:**

| Metric | Vision LSTM | Sensor SVM |
|---|---|---|
| Accuracy | 62.5% | 0.0% (see note) |
| F1 (macro) | 0.534 | 0.0% |
| Train windows | 139 | — |
| Test windows | 200 | — |
| Train epochs | 34 | — |
| Final train loss | 0.388 | — |
| Final val loss | 0.973 | — |

> **Note on sensor model:** 0% accuracy indicates the SVM trained on synthetic data does not generalize to the test split — needs real hardware data. Re-training in Phase 6.
> **Note on vision LSTM:** 62.5% on 3-class (vs. 33% chance) shows learning but is limited by small synthetic dataset. Will improve with real multi-session hardware data.

**Exit criteria: PARTIALLY MET.** Models are on disk and running. Vision LSTM below 80–85% target; both need real hardware data for full validation.

---

### Phase 5 — Weighted Late Fusion (Target: Week 3–4) — ✅ COMPLETE

- [x] **`pipeline/fusion.py`** (304 lines) — `FusionEngine` class:
  - Accepts `vision_probs` (3-class probability vector), `sensor_probs`, `visibility`, `sensor_delta`
  - **Quality-weighted fusion:** vision weight = `visibility`; sensor weight = `1 / (1 + std_dev(sensor_deltas))`; both normalized; minimum weight `1e-6`
  - Graceful single-modality fallback (camera off → sensor-only; sensor unreliable → vision-only)
  - `DEFAULT_ALERT_THRESHOLD = 0.5` (lowered for testing; configurable up to 0.99)
  - `ALERT_COOLDOWN_S = 3.0` — prevents alert spam
  - Returns dict: `{posture, confidence, alert, vision_weight, sensor_weight, fused_probs}`

**Exit criteria: MET.** Fusion engine implemented with quality weighting and graceful degradation.

---

### Phase 5b — FastAPI Backend Server & WebSocket Broadcast — ✅ COMPLETE *(not in original plan)*

- [x] **`backend/app.py`** (887 lines) — full FastAPI application:
  - Launches `VisionPipeline` and `SensorReader` in background threads on startup
  - Loads pre-trained models (`sensor_model.pkl`, `vision_lstm.pt`) if present on disk
  - **WebSocket endpoint** (`/ws`): broadcasts real-time posture state to all clients at **15 Hz** — includes sensor readings, vision features, fusion result, posture class, confidence, and alert flag
  - **REST endpoints:**
    - `GET /health` — server uptime, model load status, connection count
    - `POST /calibrate` — triggers 10s calibration, returns updated `baseline.json`
    - `POST /train` — triggers background model training (spawns subprocess)
    - `GET /training/status` — returns training job status
    - `POST /alert/threshold` — update fusion alert threshold at runtime
    - `GET /config` — current configuration
  - CORS configured for Vite dev server (port 5173)
  - `BaselineTracker` wired for live delta computation; `FusionEngine` wired to both model outputs

---

### Phase 5c — React + Vite Frontend Dashboard — ✅ COMPLETE *(not in original plan)*

- [x] **`frontend/src/App.jsx`** — main app, WebSocket hook, 15Hz state updates
- [x] **7 React components** (`frontend/src/components/`):
  - `PostureDisplay.jsx` — live posture label + confidence, color-coded status
  - `SensorPanel.jsx` — real-time bar chart of 3 sensor ADC channels (c, th, l)
  - `VisionPanel.jsx` — MediaPipe feature values + visibility score
  - `FusionGauge.jsx` — animated gauge for fused confidence + vision/sensor weights
  - `CalibrationModal.jsx` — step-by-step calibration flow with progress bar
  - `TrainingPanel.jsx` — trigger model training, display status + metrics
  - `SessionLog.jsx` — alert history log with timestamps
- [x] `start.bat` / `start.sh` scripts — launch backend + frontend together

---

### Phase 6 — Alert Integration & End-to-End Validation (Target: Week 4) — 🔶 IN PROGRESS

**Goal:** End-to-end demo on real hardware, wire-free for 1+ hour.

- [ ] Finalise compression shirt: sew sensor channels, mount motor on chest — **pending**
- [ ] Switch `SYNTHETIC = False` in `sensor_reader.py` and connect real ESP32 on `COM6`
- [ ] Validate `calibration.py` end-to-end on real hardware (produces sensible, repeatable `baseline.json`)
- [ ] Re-collect live training data with real hardware (all 3 team members, multiple sessions per posture class)
- [ ] Re-train `sensor_model` and `vision_lstm` on real data; target: sensor ~78–82%, vision LSTM ~80–85%
- [ ] Measure end-to-end latency: slouch onset → motor vibration. Target < 1s.
- [ ] Run 1-hour desk session. Log false positive count and detection rate.
- [ ] Add LiPo + TP4056 for wireless operation. Verify power-cycle behavior.

**Exit criteria:** Complete demo — sitting, slouching, correction vibration — running wire-free for minimum 1 hour. Both models retrained on real hardware data.

---

## 6. Architecture (Current State)

```
┌─────────────────────────────────────────────────────────┐
│               Frontend (Vite + React)                    │
│  PostureDisplay · SensorPanel · VisionPanel · FusionGauge│
│  CalibrationModal · TrainingPanel · SessionLog           │
└────────────────────┬────────────────────────────────────┘
                     │ WebSocket (15Hz broadcast)
                     │ REST API (calibrate, train, config)
┌────────────────────▼────────────────────────────────────┐
│               FastAPI Backend  (app.py)                  │
│                                                          │
│  ┌─────────────────────┐  ┌──────────────────────────┐  │
│  │  Vision Pipeline    │  │  Sensor Reader           │  │
│  │  (MediaPipe Pose)   │  │  (Synthetic or Serial)   │  │
│  │  vision_pipeline.py │  │  sensor_reader.py        │  │
│  └──────────┬──────────┘  └───────────┬──────────────┘  │
│             │  4 ratio features        │  3 ADC deltas    │
│             │  15-frame LSTM window    │  SVM predict     │
│             ▼                          ▼                  │
│  ┌──────────────────────────────────────────────────┐   │
│  │           Fusion Engine  (fusion.py)              │   │
│  │   Quality-weighted late fusion of probabilities   │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
         │                        │
┌────────▼──────────┐   ┌─────────▼──────────┐
│   Vision LSTM     │   │  Sensor SVM         │
│  (vision_lstm.pt) │   │  (sensor_model.pkl) │
└───────────────────┘   └────────────────────┘
         │ serial 'V' byte (when SYNTHETIC=False)
┌────────▼──────────┐
│  ESP32 + Motor    │  (currently running in synthetic mode)
└───────────────────┘
```

---

## 7. Key Design Decisions & Rationale

| Decision | Rationale |
|---|---|
| 47kΩ (not 10kΩ) voltage dividers | Better mid-range sensitivity for flex sensor operating range |
| 4 sensors, all 2.2" (changed from 3×2.2"+1×4") | Adds thoracolumbar junction (T12-L1), where desk-worker slouch originates most often; uniform sizing simplifies calibration |
| Stay on breadboard (skip perfboard) | Team decision to reduce build overhead for course project scope; accepted tradeoff is higher risk of wire looseness during wear |
| Fixed 50Hz ESP32 output | Prevents serial buffer saturation; enables predictable sliding window alignment |
| `millis()` timestamp (not true Unix time) in firmware | ESP32 has no onboard RTC; wall-clock offset established in `sensor_reader.py` on first packet received |
| 5-sample (~100ms) moving average in `sensor_reader.py` | Updated from 10-sample — 5-sample balances noise suppression with lower latency |
| EMA drift correction (alpha = 0.0005/sample) | Slow EMA tracks baseline shift from sensor temperature/sweat — **now implemented in `sensor_reader.py`** |
| Normalized ratio features (not raw pixel angles) | Scale-invariant; works regardless of webcam distance |
| Landmarks 0, 7, 8, 11, 12, 23, 24 (not just 11, 12) | Nose adds forward-head signal; hips add torso lean; ears add neck posture |
| Weighted late fusion (not naive concatenation) | Sensor and vision quality varies dynamically; weighting by quality prevents bad signal from corrupting good |
| 10s active calibration (not 15min passive EMA) | Passive EMA assumes user starts upright, which is unreliable |
| Dual-modality calibration (sensor + vision) | `baseline.json` now stores both ADC baselines and `vision_reference` features |
| Session-split train/test (not frame-split) | Prevents temporal data leakage; gives honest accuracy estimates |
| Sewn fabric channels (not tape) | Tape delaminates with sweat; channels keep sensors flat and stable |
| Transistor-based motor driver (not direct GPIO) | GPIO sources ~12–20mA max; motor draws ~70mA — direct drive risks damaging the ESP32 |
| Hardware-optional design (`SYNTHETIC` flag) | Software stack fully runnable during hardware build; seamless hardware switch |
| FastAPI + WebSocket (not polling REST) | 15Hz push-based broadcast eliminates polling overhead; supports multiple dashboard clients |
| React + Vite frontend | Fast HMR dev loop; all monitoring panels in one dashboard |

---

## 8. Known Risks & Mitigations

| Risk | Mitigation |
|---|---|
| ADC noise from motor switching | 100nF cap across motor terminals; motor wires routed away from signal wires — **confirmed sufficient in live test** |
| Wire looseness from staying on breadboard | Monitor for intermittent/flaky ADC readings; re-seat connections if noise appears |
| Sensor drift over long session | Slow EMA drift correction implemented (`EMA_ALPHA = 0.0005`) — **now live in `sensor_reader.py`** |
| MediaPipe fails in low light | Vision quality weight drops; FusionEngine falls back to sensor-only |
| User turns away from webcam | Same as above — sensor-only fallback with quality-weighted fusion |
| Sensor slips on shirt | Sewn channels, not tape; snug compression shirt fit |
| LiPo safety | Charge outside shirt; TP4056 has overcharge protection; use during testing only |
| Small dataset (synthetic-only so far) | Re-collect real hardware sessions in Phase 6; multiple sessions per person across different days |
| Firmware timestamp is boot-relative | PC-side offset established in `sensor_reader.py` on first packet |
| Sensor SVM shows 0% test accuracy | Root cause: SVM trained on synthetic data that doesn't generalize; retrain with real hardware data in Phase 6 |
| Low vision LSTM accuracy (62.5%) | Limited by small synthetic dataset; will improve with real multi-session hardware data |

---

## 9. Context for Continuing This Chat

If you are a language model reading this document to continue a prior conversation, here is the full project context:

- This is a student AIML project at RV College of Engineering. The team has purchased all hardware listed in Section 2.1.

- **Build progress (as of 2026-07-09):**
  - **Hardware (Phase 1): COMPLETE.** All 4 flex sensor voltage dividers, motor driver circuit, and ESP32 firmware built and verified.
  - **Sensor pipeline (Phase 2): COMPLETE.** `pipeline/sensor_reader.py` (597 lines) runs synthetic by default (`SYNTHETIC = True`), implements EMA drift correction (`EMA_ALPHA = 0.0005`), 5-sample moving average, `BaselineTracker` for normalized delta vectors.
  - **Calibration (Phase 2): COMPLETE.** `pipeline/calibration.py` (316 lines) does 10s dual-modality calibration; `baseline.json` is on disk with real calibration values.
  - **Vision pipeline (Phase 3): COMPLETE.** `pipeline/vision_pipeline.py` (448 lines) runs MediaPipe Pose at 30fps in a background thread, extracts 4 normalized ratio features, maintains a 15-frame sliding window.
  - **Data collection (Phase 4): COMPLETE.** `training/collect_data.py` (417 lines) supports live and synthetic modes. 6 labeled CSVs are in `backend/data/raw/`.
  - **Model training (Phase 4): COMPLETE.** SVM (`sensor_model.pkl`, 27KB) and LSTM (`vision_lstm.pt`, 218KB) trained and on disk. Vision LSTM: 62.5% accuracy; Sensor SVM: 0% (synthetic data issue — needs real hardware data).
  - **Fusion engine (Phase 5): COMPLETE.** `pipeline/fusion.py` (304 lines) quality-weighted late fusion, alert threshold 0.5, cooldown 3s.
  - **FastAPI backend (Phase 5b): COMPLETE.** `backend/app.py` (887 lines) — WebSocket at 15Hz, REST API for calibration/training/config.
  - **React frontend (Phase 5c): COMPLETE.** 7 React components covering all display and control flows.

- **Current server ports:** FastAPI on `http://localhost:8000`, Vite frontend on `http://localhost:5173`
- **Sensor mode:** `SYNTHETIC = True` (in `pipeline/sensor_reader.py` line 47) — change to `False` and set `SERIAL_PORT = "COM6"` when real ESP32 is connected
- **Next milestone (Phase 6):** Finish shirt sewing/mounting, switch to real hardware, re-collect live training data, re-train both models, end-to-end latency test.
- The team's ML experience level: intermediate (has coded before, may not have trained sequence models).
- **Key files:**
  - `firmware/esp32_sensor.ino` — firmware (DONE)
  - `backend/pipeline/sensor_reader.py` — sensor I/O + EMA drift (DONE)
  - `backend/pipeline/vision_pipeline.py` — MediaPipe (DONE)
  - `backend/pipeline/calibration.py` — calibration (DONE)
  - `backend/pipeline/fusion.py` — fusion engine (DONE)
  - `backend/app.py` — FastAPI server (DONE)
  - `backend/training/collect_data.py` — data collection (DONE)
  - `backend/training/train_sensor.py` — SVM training (DONE)
  - `backend/training/train_vision.py` — LSTM training (DONE)
  - `frontend/src/App.jsx` + 7 components — React dashboard (DONE)
