@echo off
setlocal EnableExtensions
rem Local dev: hot reload on 127.0.0.1:18026
rem Usage: scripts\dev.bat

cd /d "%~dp0.."
set "ROOT=%CD%"
if not defined MEDIACENTER_DEV_HOST set "MEDIACENTER_DEV_HOST=127.0.0.1"
if not defined MEDIACENTER_DEV_PORT if defined PORT set "MEDIACENTER_DEV_PORT=%PORT%"
if not defined MEDIACENTER_DEV_PORT set "MEDIACENTER_DEV_PORT=18026"
set "HOST=%MEDIACENTER_DEV_HOST%"
set "PORT=%MEDIACENTER_DEV_PORT%"
set "PY=%ROOT%\.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo [.venv missing] running setup_venv.bat ...
  call "%ROOT%\scripts\setup_venv.bat"
  if errorlevel 1 exit /b 1
)

if not exist "%PY%" (
  echo ERROR: python not found at %PY%
  exit /b 1
)

"%PY%" -m pip install -e "%ROOT%" -q
if errorlevel 1 exit /b 1
"%PY%" -m pip install yt-dlp -q
if errorlevel 1 exit /b 1

echo Stopping process on port %PORT% ...
call "%ROOT%\deploy\windows\kill_port_listener.bat" %PORT% python

set "MEDIACENTER_DEV_HOST=%HOST%"
set "MEDIACENTER_DEV_PORT=%PORT%"
set "PYTHONUNBUFFERED=1"

rem Sidecar: scripts\start_spider_sidecar.bat

echo ========================================
echo Family Media Center [DEV]
echo Root: %ROOT%
echo URL:  http://%HOST%:%PORT%/
echo Edit app/ for auto reload
echo Press Ctrl+C to stop
echo ========================================

"%PY%" "%ROOT%\scripts\run_dev.py"
set "EXIT_CODE=%ERRORLEVEL%"

call "%ROOT%\deploy\windows\kill_port_listener.bat" %PORT% python
exit /b %EXIT_CODE%
