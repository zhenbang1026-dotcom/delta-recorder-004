@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "主界面.py"
) else (
  python "主界面.py"
)
pause
