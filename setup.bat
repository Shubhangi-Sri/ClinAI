@echo off
REM ClinAI Local Setup Script (Windows)
REM Double-click to run, or run in Command Prompt

echo ================================================
echo   ClinAI Local Setup - Windows
echo ================================================

REM ── Backend ──────────────────────────────────────
echo.
echo [1/3] Setting up Python backend...
cd backend

python -m venv .venv
call .venv\Scripts\activate.bat

pip install --upgrade pip -q
pip install -r requirements.txt -q

if not exist routers mkdir routers
if not exist middleware mkdir middleware
if not exist audit mkdir audit

echo. > routers\__init__.py
echo. > middleware\__init__.py

echo [OK] Backend ready
cd ..

REM ── Frontend ─────────────────────────────────────
echo.
echo [2/3] Setting up React frontend...
cd frontend
call npm install
echo [OK] Frontend ready
cd ..

REM ── Instructions ─────────────────────────────────
echo.
echo ================================================
echo   Setup complete!
echo ================================================
echo.
echo NEXT STEPS:
echo.
echo 1. Edit backend\.env and add your ANTHROPIC_API_KEY
echo.
echo 2. Open TWO terminals in VS Code (Ctrl+`) :
echo.
echo    Terminal 1 - Backend:
echo    cd backend
echo    .venv\Scripts\activate
echo    python main.py
echo.
echo    Terminal 2 - Frontend:
echo    cd frontend
echo    npm start
echo.
echo 3. Open http://localhost:3000
echo ================================================
pause
