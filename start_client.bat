@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "run_client.py"
) else if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" "run_client.py"
) else (
  python "run_client.py"
)
pause
