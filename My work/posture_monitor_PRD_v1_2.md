# Product Requirements Document
# Intelligent Ergonomic Health Monitoring System
## Hybrid Posture Monitoring & Correction System

**Course:** Artificial Intelligence and Machine Learning (AI244AI)
**Team:** Anika U Bhat (1RV24CI016) · Anushka Sharan Basappa R (1RV24CI020) · Atul Roshan Naik (1RV24CI025)
**Department:** AIML, RV College of Engineering
**Document version:** 1.2 (updated — Phase 1 complete, Phase 2 in progress)
**SDG Alignment:** SDG 3 — Good Health & Well-being

---

## 1. Project Overview

### 1.1 Problem Statement

Prolonged poor posture among students and office workers causes chronic musculoskeletal disorders. Existing single-input correctors (sensor-only or camera-only) fail under real-world conditions:

- **Sensor-only** systems drift over time due to heat and mechanical memory in flex sensors
- **Camera-only** systems fail in low light or when the user turns away from the webcam
- Neither approach eliminates false positives reliably on its own

**Target users:** College students, software professionals, and remote workers spending 6–10 hours daily at a desk.

**Our solution:** A dual-input, sensor-fusion system that cross-references physical spinal curvature data (4 flex sensors + ESP32) with AI-based visual skeletal tracking (MediaPipe Pose + webcam) for highly accurate, real-time haptic correction feedback.

### 1.2 Core Value Proposition

- Eliminates false positives through redundant signal sources
- Non-intrusive: no user action required once calibrated
- Real-time: haptic feedback latency target < 1 second from slouch onset
- Wearable: compression shirt form factor, no desktop-only dependency

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
- **Output rate:** Fixed 15Hz (one JSON packet every 67ms via `delay(67)` equivalent, non-blocking `millis()` timing used in final code)
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
Cervical channel (`c`) shows a clean, isolated bend response (2080 resting → 1170 fully bent) while `th`, `l`, `tlj` remain stable. Packet timing consistent with ~67ms (15Hz) intervals.

---

## 4. Software Stack & Project Structure

### 4.1 Dependencies

| Library | Purpose |
|---|---|
| MediaPipe (`mediapipe`) | Pose landmark extraction |
| PySerial (`serial`) | ESP32 serial communication |
| NumPy, pandas | Data handling |
| PyTorch, scikit-learn | Model training |

### 4.2 Install

```bash
pip install mediapipe opencv-python pyserial torch scikit-learn numpy pandas matplotlib
```

### 4.3 Project Folder Structure

```
posture_monitor/
├── firmware/
│   └── esp32_sensor.ino        # DONE
├── data/
│   ├── raw/                    # Raw CSV session logs
│   ├── processed/               # Windowed feature arrays
│   └── baseline.json            # Calibration baseline (auto-generated)
├── models/
│   ├── sensor_model.pkl         # Trained sensor SVM/MLP
│   └── vision_lstm.pt           # Trained vision LSTM
├── pipeline/
│   ├── sensor_reader.py         # DONE — serial read + moving avg filter (10-sample window)
│   ├── vision_pipeline.py       # NEXT — MediaPipe + feature extraction
│   ├── fusion.py                # Weighted late fusion + alert logic
│   ├── calibration.py           # DONE — 10s active calibration routine
│   └── main.py                  # Entry point, ties everything together
├── training/
│   ├── collect_data.py          # Synchronized data collection script
│   ├── train_sensor.py          # Sensor model training
│   └── train_vision.py          # LSTM training
└── README.md
```

---

## 5. Implementation Plan & Progress

### Phase 1 — Hardware & Firmware (Target: Week 1) — ✅ COMPLETE

**Goal:** All 4 sensors reading stable, timestamped ADC values over serial at 15Hz.

- [x] Build one voltage divider on breadboard. Verify ADC readings with multimeter and Serial Monitor.
- [x] Build remaining 3 dividers. Confirm all 4 channels independent.
- [x] Build motor driver. Verify motor fires on GPIO HIGH, no ADC corruption.
- [x] ~~Transfer to perfboard~~ — **Team decision: staying on breadboard for the full build.** Skipped by choice, not blocked.
- [ ] Prepare compression shirt: sew sensor channels, route wiring to waist pocket, mount motor on chest.
- [x] Flash ESP32 with full sensor firmware. Verify 15Hz JSON stream with timestamps via Serial Monitor.

**Exit criteria: MET.** Serial Monitor shows clean JSON at 15Hz. All 4 ADC values change independently when sensors are bent by hand. Motor pulses cleanly on command.

**Remaining Phase 1 item:** Shirt sewing/mounting — can be done in parallel with Phase 2/3 software work since it doesn't block software development.

### Phase 2 — Active Calibration & Sensor Baseline (Target: Week 1–2) — 🔶 IN PROGRESS

- [x] Write `sensor_reader.py`: parses JSON from serial, applies moving average filter (10-sample window, ~200ms — chosen as a balanced default), auto-detects Windows COM port.
- [x] Write `calibration.py`: 10-second upright calibration, saves `baseline.json`.
- [ ] Implement slow EMA drift correction (alpha = 0.0005/sample) — **not yet added, needed before Phase 4 data collection.**
- [ ] Compute deviation of live readings from baseline as a normalized delta vector — **not yet written; needed by `fusion.py` later.**
- [ ] Run and validate `calibration.py` end-to-end on hardware (produces sensible, repeatable `baseline.json` across multiple runs).

**Exit criteria (not yet fully met):** Running `python calibration.py` produces a `baseline.json`. Live delta vector is near zero when sitting straight, non-zero when slouching.

### Phase 3 — Vision Pipeline (Target: Week 2) — NOT STARTED

- Write `vision_pipeline.py`: open webcam, run MediaPipe, extract landmarks 0, 7, 8, 11, 12, 23, 24.
- Compute 4 normalized ratio features: `fwd_head_ratio`, `shoulder_tilt`, `torso_lean`, `ear_sh_ratio`.
- Extract `visibility` score (min of shoulder + hip landmark visibility).
- Build 15-frame sliding window buffer for LSTM input.
- Verify features are stable as you move closer/farther from webcam (scale invariance check).

**Exit criteria:** `vision_pipeline.py` runs at 30fps without lag, prints stable normalized features, and visibility score drops when you turn away from camera.

### Phase 4 — Data Collection & Model Training (Target: Week 3) — NOT STARTED

- Write `collect_data.py`: simultaneously log sensor stream + vision features + manual label to CSV.
- Collect sessions: each team member contributes good/slouch/forward_head sessions (~35 min total per person).
- Process data: build windowed feature arrays for LSTM (15-frame windows), flat vectors for sensor model.
- Train `sensor_model` (SVM or MLP) using scikit-learn. Evaluate on held-out test set.
- Train `vision_lstm` (PyTorch, 2-layer LSTM). Evaluate on held-out test set.
- Log accuracy, F1, false positive rate for each model individually.

**Exit criteria:** Sensor model ~78–82% accuracy. Vision LSTM ~80–85% accuracy. Both evaluated on session-split test set (not frame-split).

### Phase 5 — Weighted Late Fusion (Target: Week 3–4) — NOT STARTED

- Write `fusion.py`: implement quality-weighted late fusion formula.
- Evaluate fused system on held-out test sessions. Compare to individual model baselines.
- Tune alert threshold (default 0.7) by sweeping precision/recall tradeoff on validation set.
- Test failure modes: cover webcam (should fall back to sensor-only), face away (same), jitter the shirt (should downweight sensor, rely on vision).

**Exit criteria:** Fused accuracy ≥ 92% on test set. Alert fires correctly under occlusion and drift conditions that break individual models.

### Phase 6 — Alert Integration & End-to-End Validation (Target: Week 4) — NOT STARTED

- Write `main.py`: thread 1 reads sensor stream; thread 2 runs vision pipeline; thread 3 runs fusion + alert.
- Integrate alert: `fusion.py` sends `'V\n'` over serial to ESP32 when threshold exceeded.
- Measure end-to-end latency: time from intentional slouch onset to motor vibration. Target < 1s.
- Run a 1-hour desk session. Measure sensor drift (baseline shift), false positive count, and detection rate.
- Add LiPo + TP4056 for wireless operation. Verify power cycle behavior.

**Exit criteria:** Complete demo — sitting, slouching, correction vibration — running wire-free for minimum 1 hour.

---

## 6. Key Design Decisions & Rationale

| Decision | Rationale |
|---|---|
| 47kΩ (not 10kΩ) voltage dividers | Better mid-range sensitivity for flex sensor operating range |
| 4 sensors, all 2.2" (changed from 3×2.2"+1×4") | Adds thoracolumbar junction (T12-L1), where desk-worker slouch originates most often; uniform sizing simplifies calibration |
| Stay on breadboard (skip perfboard) | Team decision to reduce build overhead for course project scope; accepted tradeoff is higher risk of wire looseness during wear |
| Fixed 15Hz ESP32 output | Prevents serial buffer saturation; enables predictable sliding window alignment |
| `millis()` timestamp (not true Unix time) in firmware | ESP32 has no onboard RTC; wall-clock offset will be established in `sensor_reader.py`/downstream scripts for syncing with webcam frames |
| 10-sample (~200ms) moving average in `sensor_reader.py` | Balanced smoothing — reduces noise without adding much latency; chosen as a low-effort default per team preference |
| Normalized ratio features (not raw pixel angles) | Scale-invariant; works regardless of webcam distance |
| Landmarks 0, 7, 8, 11, 12, 23, 24 (not just 11, 12) | Nose adds forward-head signal; hips add torso lean; ears add neck posture |
| Weighted late fusion (not naive concatenation) | Sensor and vision quality varies dynamically; weighting by quality prevents bad signal from corrupting good |
| 10s active calibration (not 15min passive EMA) | Passive EMA assumes user starts upright, which is unreliable |
| Session-split train/test (not frame-split) | Prevents temporal data leakage; gives honest accuracy estimates |
| Sewn fabric channels (not tape) | Tape delaminates with sweat; channels keep sensors flat and stable |
| Transistor-based motor driver (not direct GPIO) | GPIO sources ~12–20mA max; motor draws ~70mA — direct drive risks damaging the ESP32 |

---

## 7. Known Risks & Mitigations

| Risk | Mitigation |
|---|---|
| ADC noise from motor switching | 100nF cap across motor terminals; motor wires routed away from signal wires — **confirmed sufficient in live test** |
| Wire looseness from staying on breadboard | Monitor for intermittent/flaky ADC readings; re-seat connections if noise appears; consider perfboard later if reliability becomes an issue |
| Sensor drift over long session | Slow EMA drift correction (not yet implemented — planned for Phase 2 completion); re-calibration option in UI |
| MediaPipe fails in low light | Vision quality weight drops; system falls back to sensor-only |
| User turns away from webcam | Same as above — sensor-only fallback |
| Sensor slips on shirt | Sewn channels, not tape; snug compression shirt fit |
| LiPo safety | Charge outside shirt; TP4056 has overcharge protection; use during testing only |
| Small dataset (team of 3) | Collect multiple sessions per person across different days and clothing |
| Firmware timestamp is boot-relative, not wall-clock | Establish PC-side offset in `sensor_reader.py` before Phase 4 data collection |

---

## 8. Context for Continuing This Chat

If you are a language model reading this document to continue a prior conversation, here is the full project context:

- This is a student AIML project at RV College of Engineering. The team has purchased all hardware listed in Section 2.1.
- **Build progress so far (Phase 1 complete):**
  - All 4 flex sensor voltage dividers built and verified on breadboard.
  - Motor driver circuit (2N2222 + 1N4001 + 1kΩ + 100nF) built and verified — buzzes cleanly on command, no ADC interference (confirmed <±20 count jumps during motor firing).
  - Team decided to **skip perfboard entirely** and keep the final build on breadboard (accepted tradeoff: some risk of wire looseness during wear, to be monitored).
  - Full firmware (`esp32_sensor.ino`) written and flashed: reads all 4 ADC channels with 8x oversampling, outputs JSON at fixed 15Hz using `millis()`-based (boot-relative, not wall-clock) timestamps, and listens for a `'V'` byte over serial to fire a 300ms motor pulse on GPIO27.
  - Live-tested: bending S1 produced a clean, isolated drop from ~2080 (resting) to ~1170 (fully bent) while S2–S4 remained stable; timing consistent with 15Hz.
- **Phase 2 in progress:**
  - `sensor_reader.py` written: connects over serial (auto-detects Windows COM port, falls back to manual `port=` argument), parses JSON (keys: `c`, `th`, `l`, `tlj` — updated from original `s1`–`s4` to match backend expectations), applies a 10-sample (~200ms) moving average per channel, exposes a `stream()` generator and a `send_alert()` method to trigger the motor from Python.
  - `calibration.py` written: prompts user to sit upright, averages readings over 10 seconds, saves `baseline.json` with per-sensor baseline values, timestamp, and sample count. Not yet run/validated on hardware by the team.
  - **Still to do in Phase 2:** implement slow EMA drift correction (alpha = 0.0005/sample), write the normalized deviation vector computation (live − baseline) that Phase 5's fusion step will need, and validate `calibration.py` end-to-end on hardware.
- **Not yet started:** Phase 3 (vision pipeline), Phase 4 (data collection & training), Phase 5 (fusion), Phase 6 (integration & end-to-end validation). Compression shirt sewing/mounting (remaining Phase 1 hardware item) also not yet done, but doesn't block software work.
- Key changes from the original project document: added 4th sensor at thoracolumbar junction (now all 4 sensors same 2.2" size), switched to 47kΩ dividers, fixed 15Hz output rate, firmware uses boot-relative `millis()` timestamps (wall-clock sync to be handled downstream in Python), expanded MediaPipe landmarks to include nose and hips, switched from naive concatenation fusion to weighted late fusion, replaced 15-min passive EMA calibration with 10s active calibration + slow EMA drift correction (drift correction itself still pending implementation), and the team chose to stay on breadboard rather than transfer to perfboard.
- The team's ML experience level: intermediate (has coded before, may not have trained sequence models).
- Files written so far, available for reference: `firmware/esp32_sensor.ino`, `pipeline/sensor_reader.py`, `pipeline/calibration.py`.
