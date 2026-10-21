@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo ready>".venv\.ready"
".venv\Scripts\python.exe" tools\build.py
if errorlevel 1 goto :error
echo.
echo Installer is ready in release\OUTMAX-Cut-Setup-1.3.0.exe
pause
exit /b 0
:error
echo.
echo Build failed. See the error above.
pause
exit /b 1
