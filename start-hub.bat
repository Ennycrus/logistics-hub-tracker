@echo off
REM ============================================================
REM  Hub Tracker - start both servers with one double-click.
REM  Opens two windows (Backend + Frontend) and your browser.
REM  Close either window to stop that part of the app.
REM ============================================================

cd /d "%~dp0"

if not exist "backend\venv\Scripts\activate.bat" (
  echo.
  echo   Could not find the Python environment at backend\venv.
  echo   Set it up once using the README "Setup" steps, then run this again.
  echo.
  pause
  exit /b 1
)

echo Starting Hub Tracker...

REM --- Backend: Django on http://127.0.0.1:8000 ---
start "Hub Tracker - Backend" cmd /k "cd backend && call venv\Scripts\activate.bat && python manage.py runserver"

REM --- Frontend: Vite on http://localhost:5173 ---
start "Hub Tracker - Frontend" cmd /k "cd frontend && npm run dev"

REM --- Give the servers a few seconds, then open the app ---
timeout /t 6 /nobreak >nul
start "" http://localhost:5173

echo.
echo Two windows opened (Backend and Frontend). Keep them open while you work.
echo Close either window to stop that part of the app.
exit /b 0