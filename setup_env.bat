@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.11 -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py -3.11"
)
if not defined PYTHON_CMD (
  python --version | findstr /b /c:"Python 3.11" >nul
  if errorlevel 1 (
    echo 未找到 Python 3.11，请先安装 Python 3.11 x64。
    exit /b 1
  )
  set "PYTHON_CMD=python"
)

%PYTHON_CMD% -m venv .venv

".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo 环境完成。PyCharm 解释器请选择：
echo %~dp0.venv\Scripts\python.exe
pause
