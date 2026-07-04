#!/bin/bash
# setup.sh — One-time project setup script
# Creates venv, installs Python deps, installs frontend Node deps
# Run this once from the posture_monitor/ directory

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "Setting up PostureGuard in: $PROJECT_ROOT"

# ── Python virtual environment ──────────────────────────────────────────────
echo ""
echo "[1/3] Creating Python virtual environment..."
python3 -m venv "$PROJECT_ROOT/venv"
source "$PROJECT_ROOT/venv/bin/activate"

echo "[2/3] Installing Python dependencies..."
pip install --upgrade pip
pip install -r "$PROJECT_ROOT/backend/requirements.txt"

# ── Frontend Node dependencies ───────────────────────────────────────────────
echo ""
echo "[3/3] Installing frontend Node dependencies..."
cd "$PROJECT_ROOT/frontend"
npm install

# ── Create required data directories ────────────────────────────────────────
mkdir -p "$PROJECT_ROOT/backend/data/raw"
mkdir -p "$PROJECT_ROOT/backend/data/processed"
mkdir -p "$PROJECT_ROOT/backend/models"

echo ""
echo "✅ Setup complete!"
echo ""
echo "   To launch the app, run: ./start.sh"
echo "   Backend:  http://localhost:8000"
echo "   Frontend: http://localhost:5173"
