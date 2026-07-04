"""
train_vision.py — Vision LSTM Training Script
==============================================
Role in pipeline:
    Trains a 2-layer LSTM on 15-frame sliding windows of 4 normalized vision
    features extracted by vision_pipeline.py. The trained model is used by
    fusion.py to produce probability vectors for quality-weighted late fusion.

Usage:
    python training/train_vision.py

Output:
    models/vision_lstm.pt     — Saved PostureLSTM checkpoint
    models/vision_metrics.json — Accuracy, F1, confusion matrix

Expected accuracy: ~80–88% on held-out sessions (synthetic data).
Session-split train/test ensures no data leakage between sessions.
"""

import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torch.utils.data import DataLoader, TensorDataset

# ─── Constants ─────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data" / "raw"
MODELS_DIR = Path(__file__).parent.parent / "models"

# Sliding window parameters
WINDOW_SIZE = 15          # Frames per window (0.5s at 30fps)
STRIDE = 5                # Step between windows (reduces autocorrelation)

# Training hyperparameters
BATCH_SIZE = 32
LR = 1e-3                 # Initial learning rate for Adam
WEIGHT_DECAY = 1e-4       # L2 regularisation
EPOCHS = 50               # Maximum training epochs
PATIENCE = 5              # Early stopping patience (val loss)

# Data columns
VISION_COLS = ["fwd_head_ratio", "shoulder_tilt", "torso_lean", "ear_sh_ratio"]
LABEL_COL = "label"

# Integer label mapping (must match sensor trainer and fusion engine)
LABEL_MAP = {"good": 0, "slouch": 1, "forward_head": 2}
IDX_TO_LABEL = {v: k for k, v in LABEL_MAP.items()}

# Session split: hold out this fraction of sessions per label for testing
TEST_SESSION_FRACTION = 0.2

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── LSTM Architecture ──────────────────────────────────────────────────────────

class PostureLSTM(nn.Module):
    """2-layer LSTM posture classifier.

    Input shape: (batch, WINDOW_SIZE=15, 4 features)
    Output shape: (batch, 3 classes)

    Architecture mirrors the specification in the project PRD:
    LSTM → linear head with ReLU and dropout.
    """

    def __init__(self) -> None:
        """Initialise LSTM and linear classifier layers."""
        super().__init__()
        # 2-layer LSTM: processes temporal sequence of pose feature vectors
        # dropout=0.3 applied between LSTM layers (ignored for single-layer)
        self.lstm = nn.LSTM(
            input_size=4,
            hidden_size=64,
            num_layers=2,
            batch_first=True,
            dropout=0.3,
        )
        # Classification head: maps final hidden state to class logits
        self.classifier = nn.Sequential(
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, 3),  # 3 classes: good, slouch, forward_head
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Input tensor of shape (batch, seq_len=15, features=4)

        Returns:
            Logits tensor of shape (batch, 3)
        """
        out, _ = self.lstm(x)
        # Use only the final hidden state (last timestep) for classification
        return self.classifier(out[:, -1, :])


# ─── Data Loading ───────────────────────────────────────────────────────────────

def load_sessions(data_dir: Path) -> List[Tuple[pd.DataFrame, str]]:
    """Load all raw CSV sessions from the data directory.

    Args:
        data_dir: Path to directory containing labeled CSV files.

    Returns:
        List of (dataframe, label_string) tuples. Label is parsed from filename.

    Raises:
        SystemExit: If no CSV files are found or data directory missing.
    """
    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        logger.error("Run: python training/collect_data.py --generate-synthetic")
        sys.exit(1)

    csv_files = sorted(data_dir.glob("*.csv"))
    if not csv_files:
        logger.error(f"No CSV files found in {data_dir}")
        logger.error("Run: python training/collect_data.py --generate-synthetic")
        sys.exit(1)

    sessions = []
    for csv_path in csv_files:
        # Filename format: {label}_{session_id}.csv
        # Labels can contain underscores (e.g. 'forward_head'), so we match
        # greedily against known labels instead of blindly splitting on '_'.
        stem = csv_path.stem
        label = None
        for known_label in LABEL_MAP:
            if stem.startswith(known_label + "_") or stem == known_label:
                label = known_label
                break
        if label is None:
            logger.warning(f"Skipping file with unknown label: {csv_path.name}")
            continue
        try:
            df = pd.read_csv(csv_path)
            # Verify required columns exist
            missing = [c for c in VISION_COLS + [LABEL_COL] if c not in df.columns]
            if missing:
                logger.warning(f"Skipping {csv_path.name}: missing columns {missing}")
                continue
            # Drop rows with NaN in vision columns
            df = df.dropna(subset=VISION_COLS)
            if len(df) == 0:
                logger.warning(f"Skipping {csv_path.name}: all rows have NaN vision features")
                continue
            sessions.append((df, label))
            logger.debug(f"Loaded {csv_path.name}: {len(df)} rows, label={label}")
        except Exception as e:
            logger.warning(f"Failed to load {csv_path.name}: {e}")
            continue

    logger.info(f"Loaded {len(sessions)} sessions from {data_dir}")
    label_counts = Counter(label for _, label in sessions)
    for lbl, count in sorted(label_counts.items()):
        logger.info(f"  {lbl}: {count} sessions")

    return sessions


def session_split(
    sessions: List[Tuple[pd.DataFrame, str]],
    test_fraction: float = TEST_SESSION_FRACTION,
) -> Tuple[List[Tuple[pd.DataFrame, str]], List[Tuple[pd.DataFrame, str]]]:
    """Split sessions into train/test sets by session (not by frame).

    Splitting by session (not by frame) prevents data leakage — frames from
    the same recording session are highly autocorrelated.

    Args:
        sessions: List of (dataframe, label) tuples.
        test_fraction: Fraction of sessions per label to hold out for testing.

    Returns:
        Tuple of (train_sessions, test_sessions).
    """
    # Group sessions by label
    by_label: dict = {}
    for df, label in sessions:
        by_label.setdefault(label, []).append((df, label))

    train_sessions, test_sessions = [], []
    for label, label_sessions in by_label.items():
        n_test = max(1, int(len(label_sessions) * test_fraction))
        # Hold out last n_test sessions (consistent ordering = reproducible split)
        test_sessions.extend(label_sessions[-n_test:])
        train_sessions.extend(label_sessions[:-n_test])

    logger.info(
        f"Session split: {len(train_sessions)} train, {len(test_sessions)} test sessions"
    )
    return train_sessions, test_sessions


# ─── Window Creation ────────────────────────────────────────────────────────────

def create_windows(
    df: pd.DataFrame,
    window_size: int = WINDOW_SIZE,
    stride: int = STRIDE,
) -> Tuple[np.ndarray, np.ndarray]:
    """Create sliding windows of vision features from a session DataFrame.

    Args:
        df: Session DataFrame with VISION_COLS and label column.
        window_size: Number of frames per window (e.g. 15 frames = 0.5s at 30fps).
        stride: Step size between successive windows. Stride < window_size creates
                overlapping windows; reduces temporal autocorrelation vs stride=1.

    Returns:
        Tuple of:
            windows: np.ndarray of shape (N, window_size, 4)
            labels: np.ndarray of shape (N,) with integer class labels
    """
    features = df[VISION_COLS].values.astype(np.float32)  # (T, 4)
    raw_labels = df[LABEL_COL].values

    windows, labels = [], []
    for start in range(0, len(features) - window_size + 1, stride):
        end = start + window_size
        window = features[start:end]  # (window_size, 4)
        # Majority-vote label for the window (handles label transitions)
        window_labels = raw_labels[start:end]
        majority_label = Counter(window_labels).most_common(1)[0][0]
        if majority_label not in LABEL_MAP:
            continue
        windows.append(window)
        labels.append(LABEL_MAP[majority_label])

    if not windows:
        return np.empty((0, window_size, 4), dtype=np.float32), np.empty((0,), dtype=np.int64)

    return np.stack(windows, axis=0), np.array(labels, dtype=np.int64)


def sessions_to_tensors(
    sessions: List[Tuple[pd.DataFrame, str]],
    window_size: int = WINDOW_SIZE,
    stride: int = STRIDE,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Convert a list of sessions into window tensors.

    Args:
        sessions: List of (dataframe, label) tuples.
        window_size: Frames per window.
        stride: Step between windows.

    Returns:
        Tuple of (X_tensor, y_tensor) where X has shape (N, window_size, 4).
    """
    all_windows, all_labels = [], []
    for df, _ in sessions:
        w, l = create_windows(df, window_size, stride)
        if len(w) > 0:
            all_windows.append(w)
            all_labels.append(l)

    if not all_windows:
        raise ValueError("No windows created — check that CSVs contain vision feature columns.")

    X = np.concatenate(all_windows, axis=0)  # (N, 15, 4)
    y = np.concatenate(all_labels, axis=0)   # (N,)
    logger.info(f"  Windows: {X.shape}, class distribution: {Counter(y.tolist())}")
    return torch.tensor(X, dtype=torch.float32), torch.tensor(y, dtype=torch.long)


# ─── Training ───────────────────────────────────────────────────────────────────

def train_model(
    train_loader: DataLoader,
    val_loader: DataLoader,
    device: torch.device,
) -> Tuple["PostureLSTM", List[float], List[float]]:
    """Train the PostureLSTM model.

    Args:
        train_loader: DataLoader for training windows.
        val_loader: DataLoader for validation windows.
        device: CPU or CUDA device.

    Returns:
        Tuple of (best_model, train_loss_history, val_loss_history).
        Best model is the checkpoint with lowest validation loss.
    """
    model = PostureLSTM().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    # Reduce LR when validation loss stops improving (patience=5 epochs)
    # Note: verbose= was removed in PyTorch 2.x
    scheduler = ReduceLROnPlateau(optimizer, mode="min", patience=PATIENCE, factor=0.5)
    criterion = nn.CrossEntropyLoss()

    best_val_loss = float("inf")
    best_state_dict = None
    patience_counter = 0
    train_losses, val_losses = [], []

    for epoch in range(1, EPOCHS + 1):
        # ── Training phase ──────────────────────────────────────────────────
        model.train()
        epoch_train_loss = 0.0
        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            optimizer.zero_grad()
            logits = model(X_batch)
            loss = criterion(logits, y_batch)
            loss.backward()
            # Gradient clipping prevents exploding gradients in LSTM
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            epoch_train_loss += loss.item() * len(X_batch)
        epoch_train_loss /= len(train_loader.dataset)

        # ── Validation phase ────────────────────────────────────────────────
        model.eval()
        epoch_val_loss = 0.0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(device), y_batch.to(device)
                logits = model(X_batch)
                loss = criterion(logits, y_batch)
                epoch_val_loss += loss.item() * len(X_batch)
        epoch_val_loss /= len(val_loader.dataset)

        train_losses.append(epoch_train_loss)
        val_losses.append(epoch_val_loss)
        scheduler.step(epoch_val_loss)

        if epoch % 5 == 0 or epoch == 1:
            logger.info(
                f"Epoch {epoch:3d}/{EPOCHS} | "
                f"Train Loss: {epoch_train_loss:.4f} | "
                f"Val Loss: {epoch_val_loss:.4f}"
            )

        # ── Early stopping ──────────────────────────────────────────────────
        if epoch_val_loss < best_val_loss:
            best_val_loss = epoch_val_loss
            best_state_dict = {k: v.clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= PATIENCE * 2:
                logger.info(f"Early stopping triggered at epoch {epoch}")
                break

    # Restore best checkpoint
    if best_state_dict is not None:
        model.load_state_dict(best_state_dict)
    return model, train_losses, val_losses


# ─── Evaluation ─────────────────────────────────────────────────────────────────

def evaluate_model(
    model: "PostureLSTM",
    loader: DataLoader,
    device: torch.device,
) -> Tuple[np.ndarray, np.ndarray]:
    """Run model inference on a DataLoader, return predictions and ground truth.

    Args:
        model: Trained PostureLSTM model.
        loader: DataLoader of (X, y) tensors.
        device: CPU or CUDA device.

    Returns:
        Tuple of (y_true, y_pred) as numpy arrays.
    """
    model.eval()
    all_preds, all_true = [], []
    with torch.no_grad():
        for X_batch, y_batch in loader:
            logits = model(X_batch.to(device))
            preds = torch.argmax(logits, dim=1).cpu().numpy()
            all_preds.extend(preds)
            all_true.extend(y_batch.numpy())
    return np.array(all_true), np.array(all_preds)


# ─── Main ────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Main training entry point.

    Loads session CSVs, creates sliding window datasets, trains the LSTM,
    evaluates on held-out sessions, and saves the model and metrics.
    """
    logger.info("=" * 60)
    logger.info("PostureGuard — Vision LSTM Training")
    logger.info("=" * 60)

    # Device selection: use GPU if available, else CPU
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Using device: {device}")

    # Create output directory
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load and split sessions ──────────────────────────────────────────────
    logger.info("\n[1/4] Loading session data...")
    sessions = load_sessions(DATA_DIR)
    train_sessions, test_sessions = session_split(sessions)

    # ── Create window tensors ────────────────────────────────────────────────
    logger.info("\n[2/4] Creating sliding windows...")
    logger.info("  Training set:")
    X_train, y_train = sessions_to_tensors(train_sessions)
    logger.info("  Test set:")
    X_test, y_test = sessions_to_tensors(test_sessions)

    train_dataset = TensorDataset(X_train, y_train)
    test_dataset = TensorDataset(X_test, y_test)
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, drop_last=True)
    val_loader = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False)

    logger.info(f"  Train windows: {len(X_train)}, Test windows: {len(X_test)}")

    # ── Train LSTM ───────────────────────────────────────────────────────────
    logger.info(f"\n[3/4] Training LSTM ({EPOCHS} epochs, device={device})...")
    model, train_losses, val_losses = train_model(train_loader, val_loader, device)

    # Print training curve summary (first/last 3 epochs)
    logger.info("\nTraining curve summary:")
    for i, (tl, vl) in enumerate(zip(train_losses[:3], val_losses[:3])):
        logger.info(f"  Epoch  {i+1}: train={tl:.4f}, val={vl:.4f}")
    if len(train_losses) > 6:
        logger.info("  ...")
    for i in range(max(3, len(train_losses) - 3), len(train_losses)):
        logger.info(f"  Epoch {i+1:2d}: train={train_losses[i]:.4f}, val={val_losses[i]:.4f}")

    # ── Evaluate ─────────────────────────────────────────────────────────────
    logger.info("\n[4/4] Evaluating on held-out sessions...")
    y_true, y_pred = evaluate_model(model, val_loader, device)

    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1, 2])

    logger.info(f"\n{'='*50}")
    logger.info(f"  Accuracy (macro): {acc*100:.1f}%")
    logger.info(f"  F1 Score (macro): {f1:.3f}")
    logger.info(f"\n  Confusion Matrix (rows=true, cols=pred):")
    logger.info(f"  Labels: {list(LABEL_MAP.keys())}")
    logger.info(f"  {cm[0]}")
    logger.info(f"  {cm[1]}")
    logger.info(f"  {cm[2]}")
    logger.info(f"{'='*50}")

    # ── Save model ───────────────────────────────────────────────────────────
    model_path = MODELS_DIR / "vision_lstm.pt"
    try:
        torch.save(model.state_dict(), model_path)
        logger.info(f"\n✅ Saved model to: {model_path}")
    except Exception as e:
        logger.error(f"Failed to save model: {e}")
        raise

    # ── Save metrics ─────────────────────────────────────────────────────────
    metrics = {
        "accuracy": round(float(acc), 4),
        "f1_macro": round(float(f1), 4),
        "confusion_matrix": cm.tolist(),
        "train_epochs": len(train_losses),
        "final_train_loss": round(float(train_losses[-1]), 4),
        "final_val_loss": round(float(val_losses[-1]), 4),
        "n_train_windows": int(len(X_train)),
        "n_test_windows": int(len(X_test)),
    }
    metrics_path = MODELS_DIR / "vision_metrics.json"
    try:
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)
        logger.info(f"✅ Saved metrics to: {metrics_path}")
    except Exception as e:
        logger.warning(f"Failed to save metrics: {e}")

    logger.info("\nVision LSTM training complete.")
    return metrics


if __name__ == "__main__":
    main()
