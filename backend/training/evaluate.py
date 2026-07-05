"""
evaluate.py — Model Evaluation Report
======================================
Role in pipeline:
    Loads the saved sensor model (SVM/MLP) and vision LSTM from models/,
    runs evaluation on held-out sessions, and prints a side-by-side comparison
    table with accuracy, F1, and confusion matrices.

Usage:
    python training/evaluate.py

Requirements:
    - models/sensor_model.pkl and models/sensor_scaler.pkl must exist
    - models/vision_lstm.pt must exist
    - At least some CSV sessions in data/raw/ for test split
"""

import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import joblib
import torch
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix

# ─── Constants ─────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data" / "raw"
MODELS_DIR = Path(__file__).parent.parent / "models"

SENSOR_COLS = ["delta_c", "delta_th", "delta_l"]
VISION_COLS = ["fwd_head_ratio", "shoulder_tilt", "torso_lean", "ear_sh_ratio"]
LABEL_COL = "label"
LABEL_MAP = {"good": 0, "slouch": 1, "forward_head": 2}
IDX_TO_LABEL = {v: k for k, v in LABEL_MAP.items()}

WINDOW_SIZE = 15     # Must match train_vision.py
STRIDE = 5           # Must match train_vision.py
TEST_SESSION_FRACTION = 0.2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── Data Utilities (shared with trainers) ─────────────────────────────────────

def load_sessions(data_dir: Path) -> List[Tuple[pd.DataFrame, str]]:
    """Load all labeled CSV sessions.

    Args:
        data_dir: Directory containing {label}_{session_id}.csv files.

    Returns:
        List of (dataframe, label) tuples.
    """
    sessions = []
    for csv_path in sorted(data_dir.glob("*.csv")):
        # Match against known labels (handles multi-word labels like 'forward_head')
        stem = csv_path.stem
        label = None
        for known_label in LABEL_MAP:
            if stem.startswith(known_label + "_") or stem == known_label:
                label = known_label
                break
        if label is None:
            continue
        try:
            df = pd.read_csv(csv_path)
            sessions.append((df, label))
        except Exception as e:
            logger.warning(f"Failed to load {csv_path.name}: {e}")
    return sessions


def session_split(
    sessions: List[Tuple[pd.DataFrame, str]],
    test_fraction: float = TEST_SESSION_FRACTION,
) -> Tuple[List, List]:
    """Hold out a fraction of sessions per label for evaluation.

    Args:
        sessions: All loaded sessions as (df, label) tuples.
        test_fraction: Fraction to hold out per label class.

    Returns:
        Tuple of (train_sessions, test_sessions).
    """
    by_label: dict = {}
    for df, label in sessions:
        by_label.setdefault(label, []).append((df, label))

    train_sessions, test_sessions = [], []
    for label, label_sessions in by_label.items():
        n_test = max(1, int(len(label_sessions) * test_fraction))
        test_sessions.extend(label_sessions[-n_test:])
        train_sessions.extend(label_sessions[:-n_test])
    return train_sessions, test_sessions


def create_vision_windows(
    df: pd.DataFrame,
    window_size: int = WINDOW_SIZE,
    stride: int = STRIDE,
) -> Tuple[np.ndarray, np.ndarray]:
    """Create vision feature sliding windows for LSTM evaluation.

    Args:
        df: Session DataFrame.
        window_size: Frames per window.
        stride: Step between windows.

    Returns:
        Tuple of (windows shape (N,15,4), labels shape (N,)).
    """
    if not all(c in df.columns for c in VISION_COLS + [LABEL_COL]):
        return np.empty((0, window_size, 4), dtype=np.float32), np.empty((0,), dtype=np.int64)

    features = df[VISION_COLS].fillna(0).values.astype(np.float32)
    raw_labels = df[LABEL_COL].values
    windows, labels = [], []
    for start in range(0, len(features) - window_size + 1, stride):
        end = start + window_size
        window = features[start:end]
        majority_label = Counter(raw_labels[start:end]).most_common(1)[0][0]
        if majority_label not in LABEL_MAP:
            continue
        windows.append(window)
        labels.append(LABEL_MAP[majority_label])
    if not windows:
        return np.empty((0, window_size, 4), dtype=np.float32), np.empty((0,), dtype=np.int64)
    return np.stack(windows), np.array(labels, dtype=np.int64)


# ─── Sensor Model Evaluation ────────────────────────────────────────────────────

def evaluate_sensor_model(
    data_dir: Path = DATA_DIR,
    models_dir: Path = MODELS_DIR,
) -> Optional[Dict]:
    """Evaluate the saved sensor SVM/MLP model on held-out sessions.

    Args:
        data_dir: Directory containing raw CSV files.
        models_dir: Directory containing sensor_model.pkl and sensor_scaler.pkl.

    Returns:
        Dict with accuracy, f1_macro, confusion_matrix keys, or None if models
        cannot be loaded.
    """
    model_path = models_dir / "sensor_model.pkl"
    scaler_path = models_dir / "sensor_scaler.pkl"

    # ── Load model and scaler ────────────────────────────────────────────────
    try:
        model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)
        logger.info(f"Loaded sensor model: {model_path.name}")
    except FileNotFoundError as e:
        logger.warning(f"Sensor model not found: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to load sensor model: {e}")
        return None

    # ── Load and split sessions ──────────────────────────────────────────────
    sessions = load_sessions(data_dir)
    if not sessions:
        logger.warning("No sessions found for sensor evaluation.")
        return None
    _, test_sessions = session_split(sessions)

    # ── Stack test features ──────────────────────────────────────────────────
    all_X, all_y = [], []
    for df, _ in test_sessions:
        missing = [c for c in SENSOR_COLS + [LABEL_COL] if c not in df.columns]
        if missing:
            continue
        X = df[SENSOR_COLS].fillna(0).values
        y = df[LABEL_COL].map(LABEL_MAP).fillna(-1).astype(int).values
        mask = y >= 0
        all_X.append(X[mask])
        all_y.append(y[mask])

    if not all_X:
        logger.warning("No valid sensor test data found.")
        return None

    X_test = np.vstack(all_X)
    y_test = np.concatenate(all_y)

    # Apply same scaler used during training
    X_test_scaled = scaler.transform(X_test)

    # ── Predict and score ────────────────────────────────────────────────────
    y_pred = model.predict(X_test_scaled)
    acc = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred, average="macro", zero_division=0)
    cm = confusion_matrix(y_test, y_pred, labels=[0, 1, 2])

    return {
        "accuracy": float(acc),
        "f1_macro": float(f1),
        "confusion_matrix": cm.tolist(),
        "n_samples": int(len(y_test)),
        "model_type": type(model).__name__,
    }


# ─── Vision Model Evaluation ────────────────────────────────────────────────────

def evaluate_vision_model(
    data_dir: Path = DATA_DIR,
    models_dir: Path = MODELS_DIR,
) -> Optional[Dict]:
    """Evaluate the saved PostureLSTM on held-out sessions.

    Args:
        data_dir: Directory containing raw CSV files.
        models_dir: Directory containing vision_lstm.pt.

    Returns:
        Dict with accuracy, f1_macro, confusion_matrix keys, or None if the
        model cannot be loaded.
    """
    model_path = models_dir / "vision_lstm.pt"

    # ── Load LSTM ────────────────────────────────────────────────────────────
    try:
        # Import PostureLSTM from train_vision (avoids code duplication)
        sys.path.insert(0, str(Path(__file__).parent))
        from train_vision import PostureLSTM
        device = torch.device("cpu")  # Evaluation always on CPU
        model = PostureLSTM()
        state_dict = torch.load(model_path, map_location=device, weights_only=True)
        model.load_state_dict(state_dict)
        model.eval()
        logger.info(f"Loaded vision LSTM: {model_path.name}")
    except FileNotFoundError:
        logger.warning(f"Vision model not found: {model_path}")
        return None
    except Exception as e:
        logger.error(f"Failed to load vision model: {e}")
        return None

    # ── Load and split sessions ──────────────────────────────────────────────
    sessions = load_sessions(data_dir)
    if not sessions:
        logger.warning("No sessions found for vision evaluation.")
        return None
    _, test_sessions = session_split(sessions)

    # ── Create windows ───────────────────────────────────────────────────────
    all_windows, all_labels = [], []
    for df, _ in test_sessions:
        w, l = create_vision_windows(df)
        if len(w) > 0:
            all_windows.append(w)
            all_labels.append(l)

    if not all_windows:
        logger.warning("No vision windows created from test sessions.")
        return None

    X_test = torch.tensor(np.concatenate(all_windows), dtype=torch.float32)
    y_test = np.concatenate(all_labels)

    # ── Predict ──────────────────────────────────────────────────────────────
    all_preds = []
    with torch.no_grad():
        # Process in batches to avoid OOM on large datasets
        batch_size = 64
        for i in range(0, len(X_test), batch_size):
            batch = X_test[i:i+batch_size]
            logits = model(batch)
            preds = torch.argmax(logits, dim=1).numpy()
            all_preds.extend(preds)

    y_pred = np.array(all_preds)
    acc = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred, average="macro", zero_division=0)
    cm = confusion_matrix(y_test, y_pred, labels=[0, 1, 2])

    return {
        "accuracy": float(acc),
        "f1_macro": float(f1),
        "confusion_matrix": cm.tolist(),
        "n_windows": int(len(y_test)),
        "model_type": "PostureLSTM",
    }


# ─── Formatted Report ───────────────────────────────────────────────────────────

def print_report(
    sensor_metrics: Optional[Dict],
    vision_metrics: Optional[Dict],
) -> None:
    """Print a formatted side-by-side evaluation report.

    Args:
        sensor_metrics: Output from evaluate_sensor_model(), or None.
        vision_metrics: Output from evaluate_vision_model(), or None.
    """
    labels = ["good", "slouch", "forward_head"]

    print("\n" + "=" * 65)
    print("  PostureGuard — Model Evaluation Report")
    print("=" * 65)

    # ── Sensor model ─────────────────────────────────────────────────────────
    print("\n┌─ Sensor Model (SVM / MLP) ─────────────────────────────────┐")
    if sensor_metrics:
        print(f"│  Type:       {sensor_metrics['model_type']:<15}                           │")
        print(f"│  Accuracy:   {sensor_metrics['accuracy']*100:5.1f}%                                    │")
        print(f"│  F1 (macro): {sensor_metrics['f1_macro']:.3f}                                      │")
        print(f"│  Test samples: {sensor_metrics['n_samples']}                                   │")
        print("│  Confusion matrix (rows=true, cols=pred):              │")
        cm = sensor_metrics["confusion_matrix"]
        for i, row in enumerate(cm):
            row_str = "  ".join(f"{v:4d}" for v in row)
            print(f"│    {labels[i]:<14}: {row_str}                │")
    else:
        print("│  ⚠️  Model not found. Run: python training/train_sensor.py │")
    print("└────────────────────────────────────────────────────────────┘")

    # ── Vision model ─────────────────────────────────────────────────────────
    print("\n┌─ Vision LSTM ───────────────────────────────────────────────┐")
    if vision_metrics:
        print(f"│  Type:       {vision_metrics['model_type']:<15}                           │")
        print(f"│  Accuracy:   {vision_metrics['accuracy']*100:5.1f}%                                    │")
        print(f"│  F1 (macro): {vision_metrics['f1_macro']:.3f}                                      │")
        print(f"│  Test windows: {vision_metrics['n_windows']}                                  │")
        print("│  Confusion matrix (rows=true, cols=pred):              │")
        cm = vision_metrics["confusion_matrix"]
        for i, row in enumerate(cm):
            row_str = "  ".join(f"{v:4d}" for v in row)
            print(f"│    {labels[i]:<14}: {row_str}                │")
    else:
        print("│  ⚠️  Model not found. Run: python training/train_vision.py │")
    print("└────────────────────────────────────────────────────────────┘")

    # ── Comparison summary ───────────────────────────────────────────────────
    if sensor_metrics and vision_metrics:
        print("\n┌─ Comparison Summary ───────────────────────────────────────┐")
        s_acc = sensor_metrics["accuracy"] * 100
        v_acc = vision_metrics["accuracy"] * 100
        s_f1 = sensor_metrics["f1_macro"]
        v_f1 = vision_metrics["f1_macro"]
        better_acc = "Sensor" if s_acc > v_acc else "Vision"
        better_f1 = "Sensor" if s_f1 > v_f1 else "Vision"
        print(f"│  Accuracy:   Sensor {s_acc:5.1f}%  |  Vision {v_acc:5.1f}%  (↑ {better_acc})  │")
        print(f"│  F1 Macro:   Sensor {s_f1:.3f}   |  Vision {v_f1:.3f}   (↑ {better_f1})  │")
        print("│  → Both models contribute to quality-weighted fusion.   │")
        print("└────────────────────────────────────────────────────────────┘")

    print()


# ─── Main ────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Evaluate both models and print comparison report."""
    logger.info("Running evaluation on held-out sessions...")

    if not DATA_DIR.exists() or not any(DATA_DIR.glob("*.csv")):
        logger.error(f"No data found in {DATA_DIR}")
        logger.error("Run: python training/collect_data.py --generate-synthetic")
        sys.exit(1)

    sensor_metrics = evaluate_sensor_model(DATA_DIR, MODELS_DIR)
    vision_metrics = evaluate_vision_model(DATA_DIR, MODELS_DIR)

    print_report(sensor_metrics, vision_metrics)

    # Optionally load saved metrics from training (for comparison)
    for name, path in [("sensor_metrics.json", MODELS_DIR / "sensor_metrics.json"),
                       ("vision_metrics.json", MODELS_DIR / "vision_metrics.json")]:
        if path.exists():
            try:
                with open(path) as f:
                    saved = json.load(f)
                logger.info(f"Saved {name}: accuracy={saved.get('accuracy', 'N/A')}")
            except Exception:
                pass


if __name__ == "__main__":
    main()
