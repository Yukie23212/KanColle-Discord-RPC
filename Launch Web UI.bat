@echo off
cd /d "%~dp0"
python main.py --web
if errorlevel 1 (
  echo.
  echo Failed to start Discord RPC Manager Web UI.
  echo Make sure Python is installed and available as "python".
  pause
)
