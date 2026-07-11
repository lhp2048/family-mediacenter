@echo off
setlocal EnableExtensions
rem Start Family Media Center (foreground helper)

call "%~dp0resolve_app_root.bat"
if errorlevel 1 exit /b 1
if not defined PORT set "PORT=18026"
set "PY=%APP_ROOT%\.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo ERROR: .venv not found. Run service.bat install first.
  exit /b 1
)

call "%~dp0stop_service_win.bat"
set "PYTHONUNBUFFERED=1"
start "" /B "%PY%" -u -m app.main
timeout /t 2 /nobreak >nul
echo Started on port %PORT%
exit /b 0
