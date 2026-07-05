@echo off
:: start.bat — Launch backend (FastAPI) + frontend (Vite) on Windows.
:: Run this from the posture-monitor\ directory after setup.bat has completed.

setlocal

set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

:: ── Pre-flight checks ────────────────────────────────────────────────────────
if not exist "%PROJECT_ROOT%\venv" (
    echo ERROR: Virtual environment not found.
    echo        Please run setup.bat first.
    pause
    exit /b 1
)

if not exist "%PROJECT_ROOT%\frontend\node_modules" (
    echo ERROR: Node modules not found.
    echo        Please run setup.bat first.
    pause
    exit /b 1
)

echo ============================================================
echo  Starting PostureGuard...
echo ============================================================
echo.

:: ── Backend — FastAPI + uvicorn ──────────────────────────────────────────────
echo [backend]  Starting FastAPI on http://localhost:8000
echo            (opens in a new window)
start "PostureGuard - Backend" cmd /k "cd /d "%PROJECT_ROOT%\backend" && call "%PROJECT_ROOT%\venv\Scripts\activate.bat" && uvicorn app:app --reload --host 0.0.0.0 --port 8000"

:: Give the backend a moment to initialise before starting the frontend
:: uvicorn --reload spawns a subprocess which takes ~5-8s on first boot
ping -n 9 127.0.0.1 >nul

:: ── Frontend — Vite dev server ───────────────────────────────────────────────
echo [frontend] Starting Vite dev server on http://localhost:5173
echo            (opens in a new window)
start "PostureGuard - Frontend" cmd /k "cd /d "%PROJECT_ROOT%\frontend" && npm run dev"

echo.
echo ============================================================
echo  Both servers are starting in separate windows.
echo.
echo  Frontend:  http://localhost:5173
echo  Backend:   http://localhost:8000
echo  API docs:  http://localhost:8000/docs
echo.
echo  Close the two server windows (or press Ctrl+C in each)
echo  to stop the app.
echo ============================================================
endlocal
