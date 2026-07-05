@echo off
:: setup.bat — One-time project setup (Windows)
:: Creates a Python 3.12 venv, installs Python deps, and installs frontend Node deps.
:: Run this once from the posture-monitor\ directory.

setlocal

set "PROJECT_ROOT=%~dp0"
:: Strip trailing backslash
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

echo ============================================================
echo  PostureGuard — Windows Setup
echo  Project root: %PROJECT_ROOT%
echo ============================================================
echo.

:: ── Python 3.12 virtual environment ─────────────────────────────────────────
echo [1/3] Creating Python 3.12 virtual environment...
py -3.12 -m venv "%PROJECT_ROOT%\venv"
if errorlevel 1 (
    echo.
    echo ERROR: Could not create venv with Python 3.12.
    echo        Make sure Python 3.12 is installed and accessible via 'py -3.12'.
    echo        Download from: https://www.python.org/downloads/
    exit /b 1
)
echo        OK — venv created at %PROJECT_ROOT%\venv

echo.
echo [2/3] Installing Python dependencies...
"%PROJECT_ROOT%\venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
"%PROJECT_ROOT%\venv\Scripts\pip.exe" install -r "%PROJECT_ROOT%\backend\requirements.txt"
if errorlevel 1 (
    echo.
    echo ERROR: pip install failed. Check the error above.
    exit /b 1
)
echo        OK — Python packages installed.

:: ── Frontend Node dependencies ───────────────────────────────────────────────
echo.
echo [3/3] Installing frontend Node dependencies...
cd /d "%PROJECT_ROOT%\frontend"
call npm install
if errorlevel 1 (
    echo.
    echo ERROR: npm install failed.
    echo        Make sure Node.js 18+ is installed: https://nodejs.org/
    exit /b 1
)
echo        OK — Node packages installed.

:: ── Create required data/model directories ──────────────────────────────────
if not exist "%PROJECT_ROOT%\backend\data\raw"       mkdir "%PROJECT_ROOT%\backend\data\raw"
if not exist "%PROJECT_ROOT%\backend\data\processed" mkdir "%PROJECT_ROOT%\backend\data\processed"
if not exist "%PROJECT_ROOT%\backend\models"         mkdir "%PROJECT_ROOT%\backend\models"

echo.
echo ============================================================
echo  Setup complete!
echo.
echo  To launch the app, run:   start.bat
echo  Backend:   http://localhost:8000
echo  Frontend:  http://localhost:5173
echo  API docs:  http://localhost:8000/docs
echo ============================================================
endlocal
