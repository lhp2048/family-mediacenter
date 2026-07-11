@echo off
setlocal EnableExtensions
rem Background Family Media Center process (for scheduled task)

call "%~dp0resolve_app_root.bat"
if errorlevel 1 exit /b 1
if not defined PORT set "PORT=18026"
set "PY=%APP_ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" exit /b 1

set "PYTHONUNBUFFERED=1"
start "" /B "%PY%" -u -m app.main
exit /b 0
