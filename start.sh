#!/bin/bash
# start.sh — Launch both backend (FastAPI) and frontend (Vite) servers
# Run from the posture_monitor/ directory after running setup.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Check venv exists
if [ ! -d "$PROJECT_ROOT/venv" ]; then
  echo "❌ Virtual environment not found. Please run ./setup.sh first."
  exit 1
fi

# Check node_modules exists
if [ ! -d "$PROJECT_ROOT/frontend/node_modules" ]; then
  echo "❌ Node modules not found. Please run ./setup.sh first."
  exit 1
fi

echo "🚀 Starting PostureGuard..."
echo ""

# ── Backend ──────────────────────────────────────────────────────────────────
echo "[backend] Starting FastAPI on http://localhost:8000"
cd "$PROJECT_ROOT/backend"
source "$PROJECT_ROOT/venv/bin/activate"
uvicorn app:app --reload --port 8000 &
BACKEND_PID=$!
echo "[backend] PID: $BACKEND_PID"

# Give backend a moment to start
sleep 2

# ── Frontend ─────────────────────────────────────────────────────────────────
echo ""
echo "[frontend] Starting Vite dev server on http://localhost:5173"
cd "$PROJECT_ROOT/frontend"
npm run dev &
FRONTEND_PID=$!
echo "[frontend] PID: $FRONTEND_PID"

echo ""
echo "✅ Both servers running."
echo "   Frontend: http://localhost:5173"
echo "   Backend:  http://localhost:8000/docs"
echo ""
echo "   Press Ctrl+C to stop both."

# Wait and clean up on interrupt
trap "echo ''; echo 'Stopping servers...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
