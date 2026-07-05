"""
PostureGuard FastAPI Backend Server
====================================
Main application entry-point for the PostureGuard posture monitoring system.

Responsibilities:
  - Launches the vision pipeline (MediaPipe) and sensor reader in background threads.
  - Loads pre-trained ML models (sensor classifier + vision LSTM) when available.
  - Broadcasts real-time posture state to all connected WebSocket clients at ~15 Hz.
  - Exposes REST endpoints for health checks, calibration, training, and configuration.

Usage::

    uvicorn app:app --host 0.0.0.0 --port 8000 --reload

Author: PostureGuard Team
"""

import asyncio
import json
import logging
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Pipeline imports
# ---------------------------------------------------------------------------
from pipeline.sensor_reader import BaselineTracker, SyntheticSensorReader, create_reader
from pipeline.vision_pipeline import get_pipeline, start_pipeline
from pipeline.calibration import BASELINE_PATH, is_calibrated, load_baseline, run_calibration
from pipeline.fusion import FusionEngine

# ===========================================================================
# CONSTANTS
# ===========================================================================

BROADCAST_HZ: int = 15          # WebSocket broadcast rate (frames per second)
MODELS_DIR: Path = Path(__file__).parent / "models"   # Pre-trained model artefacts
DATA_DIR: Path = Path(__file__).parent / "data"        # Collected training data
LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# Duration (seconds) for a single calibration pass
CALIBRATION_DURATION_S: int = 10

# Python interpreter inside the project venv.
# On Windows venvs use Scripts\python.exe; on Unix it's bin/python.
_VENV_PYTHON: str = str(
    Path(sys.executable).parent.parent / "venv" / "Scripts" / "python.exe"
    if sys.platform == "win32"
    else Path(sys.executable)  # already the venv python when launched from venv
)
# Fallback: if the computed path doesn't exist, just use the current interpreter
if not Path(_VENV_PYTHON).exists():
    _VENV_PYTHON = str(Path(sys.executable))

# Sensor keys used throughout the application
SENSOR_KEYS: tuple[str, ...] = ("c", "th", "l", "tlj")

# ===========================================================================
# MODULE-LEVEL APPLICATION STATE
# ===========================================================================

sensor_reader = None                     # Active sensor reader instance
baseline_tracker: Optional[BaselineTracker] = None   # Tracks running baseline
vision_pipeline_instance = None          # Vision pipeline handle
fusion_engine: Optional[FusionEngine] = None         # Sensor+vision fusion

sensor_model = None                      # Trained sklearn sensor classifier
sensor_scaler = None                     # Paired feature scaler
vision_model = None                      # Trained PyTorch LSTM model

connected_clients: list[WebSocket] = []  # Active WebSocket connections

latest_sensor_sample = None              # Most recent sensor reading (dict)
latest_sensor_lock = threading.Lock()    # Guards latest_sensor_sample

# Wall-clock time the server started (used for /health uptime)
_server_start_time: float = time.time()

# Flags set after model loading attempts (populated during startup)
_models_loaded: dict[str, bool] = {"sensor": False, "vision": False}

# ---------------------------------------------------------------------------
# Logging — configured once at module level so all loggers inherit the format
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("postureguard.app")


# ===========================================================================
# MODEL LOADING
# ===========================================================================


def load_models() -> dict[str, bool]:
    """Load all pre-trained ML models from *MODELS_DIR* if they exist.

    Attempts to load:
      - ``models/sensor_model.pkl``  — scikit-learn posture classifier.
      - ``models/sensor_scaler.pkl`` — paired StandardScaler.
      - ``models/vision_lstm.pt``    — PyTorch LSTM for skeleton sequences.

    Returns
    -------
    dict[str, bool]
        ``{"sensor_loaded": bool, "vision_loaded": bool}``
    """
    global sensor_model, sensor_scaler, vision_model

    result: dict[str, bool] = {"sensor_loaded": False, "vision_loaded": False}

    # ── Sensor model (sklearn / joblib) ────────────────────────────────────
    sensor_model_path = MODELS_DIR / "sensor_model.pkl"
    sensor_scaler_path = MODELS_DIR / "sensor_scaler.pkl"
    try:
        import joblib  # local import — optional dependency

        if sensor_model_path.exists() and sensor_scaler_path.exists():
            sensor_model = joblib.load(sensor_model_path)
            sensor_scaler = joblib.load(sensor_scaler_path)
            result["sensor_loaded"] = True
            logger.info("Sensor model loaded from %s", sensor_model_path)
        else:
            logger.warning(
                "Sensor model not found at %s — rule-based fallback active",
                sensor_model_path,
            )
    except Exception as exc:
        logger.error("Failed to load sensor model: %s", exc)

    # ── Vision LSTM (PyTorch) ───────────────────────────────────────────────
    vision_model_path = MODELS_DIR / "vision_lstm.pt"
    try:
        import torch  # local import — optional dependency
        import sys as _sys
        # PostureLSTM is defined in training/train_vision.py
        _training_dir = str(Path(__file__).parent / "training")
        if _training_dir not in _sys.path:
            _sys.path.insert(0, _training_dir)
        from train_vision import PostureLSTM  # noqa: E402

        if vision_model_path.exists():
            vision_model = PostureLSTM()
            state = torch.load(vision_model_path, map_location="cpu", weights_only=True)
            vision_model.load_state_dict(state)
            vision_model.eval()
            result["vision_loaded"] = True
            logger.info("Vision LSTM loaded from %s", vision_model_path)
        else:
            logger.warning(
                "Vision model not found at %s — vision inference unavailable",
                vision_model_path,
            )
    except Exception as exc:
        logger.error("Failed to load vision model: %s", exc)

    # Update global flags so /status can report accurately
    _models_loaded["sensor"] = result["sensor_loaded"]
    _models_loaded["vision"] = result["vision_loaded"]

    return result


# ===========================================================================
# SENSOR BACKGROUND THREAD
# ===========================================================================


def _sensor_thread_fn() -> None:
    """Continuously poll the sensor reader and store the latest sample.

    Runs as a daemon thread started during application startup.  Acquires
    ``latest_sensor_lock`` only for the brief assignment so the broadcast
    coroutine is never blocked for long.
    """
    global latest_sensor_sample

    logger.info("Sensor thread started (reader type: %s)", type(sensor_reader).__name__)

    while True:
        try:
            sample = sensor_reader.get_sample()  # returns latest dict from reader
            if sample is not None:
                with latest_sensor_lock:
                    latest_sensor_sample = sample
            time.sleep(1.0 / 50)  # poll at 50 Hz max
        except Exception as exc:
            logger.warning("Sensor read error: %s — retrying in 50 ms", exc)
            time.sleep(0.05)


# ===========================================================================
# FASTAPI APPLICATION
# ===========================================================================

app = FastAPI(
    title="PostureGuard API",
    version="1.0.0",
    description=(
        "Real-time posture monitoring API — fuses ESP32 flex sensor data with "
        "MediaPipe skeleton features to classify posture and trigger alerts."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===========================================================================
# STARTUP / SHUTDOWN
# ===========================================================================


@app.on_event("startup")
async def startup_event() -> None:
    """Initialise all pipeline components when the ASGI server starts.

    Steps
    -----
    1. Ensure data/model directories exist.
    2. Create sensor reader & baseline tracker.
    3. Launch sensor reader in a daemon thread.
    4. Start the MediaPipe vision pipeline.
    5. Load pre-trained models (non-blocking — failures are logged, not raised).
    6. Instantiate the FusionEngine.
    """
    global sensor_reader, baseline_tracker, vision_pipeline_instance, fusion_engine

    logger.info("=== PostureGuard API starting up ===")

    # ── Directory scaffolding ───────────────────────────────────────────────
    try:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Ensured directories: %s, %s", MODELS_DIR, DATA_DIR)
    except OSError as exc:
        logger.error("Could not create required directories: %s", exc)

    # ── Sensor reader ───────────────────────────────────────────────────────
    try:
        sensor_reader = create_reader()
        # BaselineTracker takes an optional Path; it loads JSON from file if it exists
        baseline_tracker = BaselineTracker(BASELINE_PATH if BASELINE_PATH.exists() else None)
        logger.info("Sensor reader created; baseline loaded from %s", BASELINE_PATH)
    except Exception as exc:
        logger.warning("Sensor reader setup failed (%s) — using synthetic reader", exc)
        sensor_reader = SyntheticSensorReader()
        baseline_tracker = BaselineTracker({})

    # Start sensor polling thread (daemon=True so it dies with the server)
    sensor_thread = threading.Thread(
        target=_sensor_thread_fn,
        name="sensor-reader",
        daemon=True,
    )
    sensor_thread.start()
    logger.info("Sensor thread launched (tid=%s)", sensor_thread.ident)

    # ── Vision pipeline ─────────────────────────────────────────────────────
    try:
        # start_pipeline() creates AND starts the pipeline (returns the instance)
        vision_pipeline_instance = start_pipeline()
        logger.info("Vision pipeline started: %s", type(vision_pipeline_instance).__name__)
    except Exception as exc:
        logger.warning("Vision pipeline could not start: %s", exc)
        vision_pipeline_instance = None

    # ── ML models ───────────────────────────────────────────────────────────
    model_status = load_models()
    logger.info("Model load result: %s", model_status)

    # ── Fusion engine ───────────────────────────────────────────────────────
    try:
        fusion_engine = FusionEngine()
        logger.info("FusionEngine ready")
    except Exception as exc:
        logger.error("FusionEngine init failed: %s", exc)
        fusion_engine = None

    logger.info("=== Startup complete — broadcasting at %d Hz ===", BROADCAST_HZ)


# ===========================================================================
# HELPER — BUILD BROADCAST PAYLOAD
# ===========================================================================


def _rule_based_posture(delta: dict[str, float]) -> tuple[str, float, bool]:
    """Derive posture label, confidence, and alert flag from raw sensor deltas.

    Used as a fallback when ML models are not loaded.

    Parameters
    ----------
    delta:
        Mapping of sensor key → fractional delta from baseline.

    Returns
    -------
    tuple[str, float, bool]
        ``(posture_label, confidence, alert)``
    """
    c_delta = delta.get("c", 0.0)
    th_delta = delta.get("th", 0.0)
    l_delta = delta.get("l", 0.0)
    tlj_delta = delta.get("tlj", 0.0)

    # If both cervical and thoracic drop substantially → forward head
    if c_delta < -0.15 and th_delta < -0.10:
        confidence = min(1.0, abs(c_delta) + abs(th_delta))
        return "forward_head", round(confidence, 2), True

    # If lumbar or thoracic drops substantially → slouch
    if l_delta < -0.15 or th_delta < -0.15:
        confidence = min(1.0, abs(l_delta) + abs(th_delta))
        return "slouch", round(confidence, 2), True

    # Good posture
    magnitude = abs(c_delta) + abs(th_delta) + abs(l_delta) + abs(tlj_delta)
    confidence = max(0.5, 1.0 - magnitude)
    return "good", round(confidence, 2), False


def _build_broadcast_payload() -> dict:
    """Assemble the full WebSocket broadcast message from current pipeline state.

    Merges data from the sensor reader, vision pipeline, and fusion engine.
    Falls back gracefully to rule-based heuristics if models are unavailable.

    Returns
    -------
    dict
        JSON-serialisable message conforming to the broadcast schema.
    """
    now_ms: int = int(time.time() * 1000)

    # ── Sensor data ─────────────────────────────────────────────────────────
    with latest_sensor_lock:
        sample = latest_sensor_sample

    if sample is not None:
        raw: dict[str, int] = {
            k: int(sample.get(k, 0)) for k in SENSOR_KEYS
        }
        delta: dict[str, float] = {}
        quality_sensor: float = float(sample.get("quality", 0.75))

        if baseline_tracker is not None:
            baseline_vals = baseline_tracker.get_baseline()  # returns dict keyed by 'c','th','l','tlj'
            for k in SENSOR_KEYS:
                baseline_val = baseline_vals.get(k, 0)
                if baseline_val and baseline_val != 0:
                    delta[k] = round((raw[k] - baseline_val) / baseline_val, 3)
                else:
                    delta[k] = 0.0
        else:
            delta = {k: 0.0 for k in SENSOR_KEYS}
    else:
        raw = {k: 0 for k in SENSOR_KEYS}
        delta = {k: 0.0 for k in SENSOR_KEYS}
        quality_sensor = 0.0

    sensor_payload = {
        "raw": raw,
        "delta": delta,
        "quality": quality_sensor,
    }

    # ── Vision data ──────────────────────────────────────────────────────────
    vision_features: dict[str, float] = {}
    vision_visibility: float = 0.0
    quality_vision: float = 0.0

    if vision_pipeline_instance is not None:
        try:
            # get_state() returns {"features": List[List[float]] shape (WINDOW_SIZE,4),
            # "visibility": float, "timestamp_ms": float}
            vision_data = vision_pipeline_instance.get_state()
            if vision_data and vision_data.get("features"):
                window = vision_data["features"]  # shape (15, 4)
                # Use last row = most recent frame for per-feature display
                feats = window[-1] if window else []
                if len(feats) == 4:
                    vision_features = {
                        "fwd_head_ratio": round(float(feats[0]), 3),
                        "shoulder_tilt":  round(float(feats[1]), 3),
                        "torso_lean":     round(float(feats[2]), 3),
                        "ear_sh_ratio":   round(float(feats[3]), 3),
                    }
                vision_visibility = round(float(vision_data.get("visibility", 0.0)), 3)
                quality_vision = vision_visibility  # visibility IS the quality score
        except Exception as exc:
            logger.debug("Vision data fetch error: %s", exc)

    vision_payload = {
        "features": vision_features,
        "visibility": vision_visibility,
        "quality": quality_vision,
    }

    # ── Fusion / inference ───────────────────────────────────────────────────
    posture: str
    confidence: float
    alert: bool
    probabilities: dict[str, float]
    weights: dict[str, float]

    if fusion_engine is not None and (_models_loaded["sensor"] or _models_loaded["vision"]):
        try:
            import numpy as _np
            import torch as _torch

            # ── Build sensor probability vector ─────────────────────────────
            sensor_probs = None
            delta_arr = _np.array([delta.get(k, 0.0) for k in SENSOR_KEYS], dtype=_np.float32)
            if sensor_model is not None and sensor_scaler is not None:
                delta_scaled = sensor_scaler.transform(delta_arr.reshape(1, -1))
                raw_probs = sensor_model.predict_proba(delta_scaled)[0]
                sensor_probs = _np.array(raw_probs, dtype=_np.float64)

            # ── Build vision probability vector ──────────────────────────────
            vision_probs = None
            if vision_model is not None and vision_pipeline_instance is not None:
                vision_state = vision_pipeline_instance.get_state()
                # "features" key holds the full (WINDOW_SIZE, 4) window
                window = vision_state.get("features")
                if window and len(window) == 15:
                    window_arr = _np.array(window, dtype=_np.float32)  # (15, 4)
                    
                    # Shift live features to match the synthetic baseline the model was trained on
                    synthetic_vision_baseline = _np.array([1.20, 0.02, 1.80, 0.90], dtype=_np.float32)
                    user_vision_baseline = _np.array(
                        baseline_tracker.get_baseline().get("vision_reference", [1.20, 0.02, 1.80, 0.90]), 
                        dtype=_np.float32
                    )
                    shift = synthetic_vision_baseline - user_vision_baseline
                    window_arr = window_arr + shift

                    x = _torch.tensor(window_arr).unsqueeze(0)  # (1, 15, 4)
                    with _torch.no_grad():
                        logits = vision_model(x)
                        vision_probs = _torch.softmax(logits, dim=1).numpy()[0]

            if sensor_probs is None and vision_probs is None:
                raise ValueError("No model outputs available")

            fusion_result = fusion_engine.predict(
                vision_probs=vision_probs,
                sensor_probs=sensor_probs,
                visibility=vision_visibility,
                sensor_delta=delta_arr,
            )
            posture = fusion_result["posture"]
            confidence = fusion_result["confidence"]
            alert = fusion_result["alert"]
            probabilities = fusion_result["probabilities"]
            weights = fusion_result["weights"]
        except Exception as exc:
            logger.debug("Fusion inference error: %s — using rule-based fallback", exc)
            posture, confidence, alert = _rule_based_posture(delta)
            probabilities = {posture: confidence}
            weights = {"vision": 0.5, "sensor": 0.5}
    else:
        # No models loaded — pure heuristic
        posture, confidence, alert = _rule_based_posture(delta)
        # Simple probability distribution
        base_good = max(0.0, 1.0 - confidence) if posture != "good" else confidence
        probabilities = {
            "good": round(base_good, 3),
            posture: round(confidence, 3) if posture != "good" else round(confidence, 3),
        }
        if posture == "good":
            probabilities = {"good": confidence, "slouch": round(1 - confidence, 3), "forward_head": 0.0}
        else:
            remaining = round(1.0 - confidence - base_good, 3)
            other = "forward_head" if posture == "slouch" else "slouch"
            probabilities = {
                "good": base_good,
                posture: confidence,
                other: max(0.0, remaining),
            }
        weights = {"vision": 0.0, "sensor": 1.0}

    fusion_payload = {
        "weights": weights,
        "probabilities": probabilities,
    }

    return {
        "timestamp": now_ms,
        "posture": posture,
        "confidence": confidence,
        "alert": alert,
        "sensor": sensor_payload,
        "vision": vision_payload,
        "fusion": fusion_payload,
    }


# ===========================================================================
# REST ENDPOINTS
# ===========================================================================


@app.get("/health", response_class=JSONResponse, tags=["Monitoring"])
async def health() -> dict:
    """Return a lightweight liveness probe.

    Returns
    -------
    dict
        ``{"status": "ok", "timestamp": ISO-8601, "uptime_s": float}``
    """
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "uptime_s": round(time.time() - _server_start_time, 2),
    }


@app.get("/status", response_class=JSONResponse, tags=["Monitoring"])
async def status() -> dict:
    """Return the full system status.

    Returns
    -------
    dict
        Calibration state, model availability, camera availability, etc.
    """
    camera_ok: bool = vision_pipeline_instance is not None
    synthetic: bool = isinstance(sensor_reader, SyntheticSensorReader)
    threshold: float = fusion_engine.threshold if fusion_engine else 0.60

    baseline = load_baseline()
    
    return {
        "calibrated": is_calibrated(),
        "last_calibrated": baseline.get("calibrated_at") if baseline else None,
        "baseline_data": baseline,
        "models_loaded": {
            "sensor": _models_loaded.get("sensor", False),
            "vision": _models_loaded.get("vision", False),
        },
        "synthetic_mode": synthetic,
        "camera_available": camera_ok,
        "alert_threshold": threshold,
    }


# ── Pydantic request bodies ─────────────────────────────────────────────────


class ThresholdBody(BaseModel):
    """Request body for the POST /alert-threshold endpoint."""

    threshold: float


# ── Calibration ─────────────────────────────────────────────────────────────


def _calibration_task() -> None:
    """Background task that runs the calibration procedure and updates the tracker.

    Runs ``run_calibration()`` (blocks for ~10 s), then reloads the baseline
    into ``baseline_tracker`` so future delta calculations use the new reference.
    """
    global baseline_tracker

    logger.info("Calibration task started (duration=%d s)", CALIBRATION_DURATION_S)
    try:
        run_calibration(sensor_reader, vision_pipeline_instance)
        new_baseline = load_baseline()
        baseline_tracker = BaselineTracker(BASELINE_PATH)
        logger.info("Calibration complete — baseline updated: %s", new_baseline)
    except Exception as exc:
        logger.error("Calibration task failed: %s", exc)


@app.post("/calibrate", response_class=JSONResponse, tags=["Configuration"])
async def calibrate(background_tasks: BackgroundTasks) -> dict:
    """Trigger a background calibration pass (~10 s).

    Starts ``run_calibration()`` in a FastAPI background task so the HTTP
    response is returned immediately while calibration runs asynchronously.

    Returns
    -------
    dict
        ``{"status": "calibrating", "duration_s": int}``
    """
    background_tasks.add_task(_calibration_task)
    logger.info("Calibration requested — running in background")
    return {"status": "calibrating", "duration_s": CALIBRATION_DURATION_S}


# ── Training ─────────────────────────────────────────────────────────────────


def _run_training_task(synthetic: bool) -> None:
    """Execute the full training pipeline as subprocesses.

    Steps
    -----
    1. (If *synthetic*) ``collect_data.py --generate-synthetic``
    2. ``train_sensor.py``
    3. ``train_vision.py``
    4. Reload models into global state.

    Parameters
    ----------
    synthetic:
        When ``True``, synthetic data is generated before training.
    """
    scripts_dir = Path(__file__).parent

    def _run(script: str, *args: str) -> bool:
        """Run *script* as a subprocess; return ``True`` on success."""
        cmd = [_VENV_PYTHON, str(scripts_dir / script), *args]
        logger.info("Running subprocess: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(scripts_dir),
                timeout=600,
            )
            if result.returncode == 0:
                logger.info("%s completed successfully:\n%s", script, result.stdout[-2000:])
                return True
            else:
                logger.error("%s failed (rc=%d):\n%s", script, result.returncode, result.stderr[-2000:])
                return False
        except subprocess.TimeoutExpired:
            logger.error("%s timed out after 600 s", script)
            return False
        except Exception as exc:
            logger.error("Error running %s: %s", script, exc)
            return False

    if synthetic:
        logger.info("Generating synthetic training data …")
        _run("training/collect_data.py", "--generate-synthetic")

    logger.info("Training sensor model …")
    _run("training/train_sensor.py")

    logger.info("Training vision model …")
    _run("training/train_vision.py")

    logger.info("Reloading models after training …")
    load_models()


@app.post("/train", response_class=JSONResponse, tags=["Training"])
async def train(background_tasks: BackgroundTasks, synthetic: bool = True) -> dict:
    """Kick off the training pipeline in the background.

    Parameters
    ----------
    synthetic:
        If ``True`` (default), synthetic data is generated before training.

    Returns
    -------
    dict
        ``{"status": "training_started", "synthetic": bool}``
    """
    background_tasks.add_task(_run_training_task, synthetic)
    logger.info("Training task enqueued (synthetic=%s)", synthetic)
    return {"status": "training_started", "synthetic": synthetic}


# ── Alert threshold ──────────────────────────────────────────────────────────


@app.post("/alert-threshold", response_class=JSONResponse, tags=["Configuration"])
async def set_alert_threshold(body: ThresholdBody) -> dict:
    """Update the alert confidence threshold used by the FusionEngine.

    Parameters
    ----------
    body:
        JSON body containing ``{"threshold": float}`` (must be in [0, 1]).

    Returns
    -------
    dict
        ``{"threshold": float}``

    Raises
    ------
    HTTPException
        400 if the threshold is outside [0.0, 1.0].
        503 if the FusionEngine has not been initialised.
    """
    if not 0.0 <= body.threshold <= 1.0:
        raise HTTPException(
            status_code=400,
            detail=f"Threshold must be in [0.0, 1.0]; got {body.threshold}",
        )
    if fusion_engine is None:
        raise HTTPException(status_code=503, detail="FusionEngine not initialised")

    fusion_engine.update_threshold(body.threshold)
    logger.info("Alert threshold updated → %.3f", body.threshold)
    return {"threshold": body.threshold}


# ── Recording endpoints (for TrainingPanel live data collection) ─────────────

_recording_active: bool = False
_recording_label: str = ""
_recording_rows: list = []


@app.post("/record/start", response_class=JSONResponse, tags=["Training"])
async def record_start(label: str = "good") -> dict:
    """Start a live data recording session for the given posture label.

    Parameters
    ----------
    label:
        Posture class to record: "good", "slouch", or "forward_head".

    Returns
    -------
    dict
        ``{"status": "recording", "label": str}``
    """
    global _recording_active, _recording_label, _recording_rows
    if label not in ("good", "slouch", "forward_head"):
        raise HTTPException(status_code=400, detail=f"Unknown label: {label}")
    _recording_active = True
    _recording_label = label
    _recording_rows = []
    logger.info("Recording started for label='%s'", label)
    return {"status": "recording", "label": label}


@app.post("/record/stop", response_class=JSONResponse, tags=["Training"])
async def record_stop() -> dict:
    """Stop the current recording session and save the CSV to data/raw/.

    Returns
    -------
    dict
        ``{"status": "saved", "rows": int, "file": str}`` on success.
    """
    global _recording_active, _recording_label, _recording_rows
    if not _recording_active:
        return {"status": "not_recording"}

    _recording_active = False
    rows = _recording_rows.copy()
    label = _recording_label
    _recording_rows = []

    if rows:
        import pandas as _pd, uuid as _uuid
        from datetime import datetime as _dt
        session_id = _uuid.uuid4().hex[:8]
        filename = f"{label}_{session_id}.csv"
        out_path = DATA_DIR / "raw" / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            _pd.DataFrame(rows).to_csv(out_path, index=False)
            logger.info("Recording saved: %s (%d rows)", out_path, len(rows))
            return {"status": "saved", "rows": len(rows), "file": filename}
        except Exception as exc:
            logger.error("Failed to save recording: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "saved", "rows": 0, "file": ""}

from fastapi.responses import StreamingResponse

@app.get("/video_feed", tags=["Monitoring"])
async def video_feed():
    """Live MJPEG video stream from the vision pipeline."""
    async def frame_generator():
        while True:
            if vision_pipeline_instance:
                jpeg = vision_pipeline_instance.get_latest_jpeg()
                if jpeg:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
            await asyncio.sleep(1.0 / BROADCAST_HZ)

    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")



# ===========================================================================
# WEBSOCKET — REAL-TIME BROADCAST
# ===========================================================================


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Accept a WebSocket connection and stream posture state at BROADCAST_HZ.

    The endpoint adds the client to ``connected_clients`` on connect and
    removes it on disconnect or error.  Each loop iteration builds the full
    broadcast payload and sends it as a JSON string.

    Broadcast message schema::

        {
            "timestamp":  int,    # Unix ms
            "posture":    str,    # "good" | "slouch" | "forward_head"
            "confidence": float,
            "alert":      bool,
            "sensor":     {...},
            "vision":     {...},
            "fusion":     {...}
        }
    """
    await websocket.accept()
    connected_clients.append(websocket)
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.info("WebSocket client connected: %s (total=%d)", client_host, len(connected_clients))

    frame_interval: float = 1.0 / BROADCAST_HZ

    try:
        while True:
            loop_start = asyncio.get_event_loop().time()

            try:
                payload = _build_broadcast_payload()
                await websocket.send_text(json.dumps(payload))
            except Exception as exc:
                logger.warning("Broadcast error for %s: %s", client_host, exc)
                break

            # Sleep for the remainder of the frame budget
            elapsed = asyncio.get_event_loop().time() - loop_start
            sleep_time = max(0.0, frame_interval - elapsed)
            await asyncio.sleep(sleep_time)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected: %s", client_host)
    except Exception as exc:
        logger.warning("WebSocket unexpected error (%s): %s", client_host, exc)
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        logger.info(
            "WebSocket client removed: %s (remaining=%d)", client_host, len(connected_clients)
        )
