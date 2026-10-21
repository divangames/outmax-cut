@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto :error
)
if not exist ".venv\.ready" (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :error
  echo ready>".venv\.ready"
)
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :error
exit /b 0
:error
echo.
echo Could not start OUTMAX Cut. See the error above.
echo Requires Python 3.11-3.13 and FFmpeg on the build computer.
pause
exit /b 1
