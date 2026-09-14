@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
echo FLY / POOL - http://127.0.0.1:8766
echo Save memory before closing. Ctrl+C requests an orderly shutdown.
".venv\Scripts\python.exe" -m biliardo.launcher
pause
