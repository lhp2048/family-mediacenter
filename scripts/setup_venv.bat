@echo off
setlocal EnableExtensions
rem Create or refresh .venv for local development (Python 3.10+)

cd /d "%~dp0.."
set "ROOT=%CD%"

echo [Family Media Center] setup .venv

call "%ROOT%\deploy\windows\resolve_python.bat"
if errorlevel 1 exit /b 1

if exist "%ROOT%\.venv\Scripts\python.exe" (
  "%ROOT%\.venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
  if errorlevel 1 (
    echo Removing old .venv - Python too old
    rmdir /s /q "%ROOT%\.venv"
  )
)

if not exist "%ROOT%\.venv\Scripts\python.exe" (
  echo Creating venv...
  %PY_BOOTSTRAP% -m venv "%ROOT%\.venv"
  if errorlevel 1 exit /b 1
)

set "PY=%ROOT%\.venv\Scripts\python.exe"
"%PY%" -m pip install -U pip setuptools wheel -q
"%PY%" -m pip install -e "%ROOT%" -q
"%PY%" -m pip install yt-dlp -q

"%PY%" -c "import uvicorn; from app.main import app" >nul 2>&1
if errorlevel 1 (
  echo ERROR: import verify failed
  exit /b 1
)

if not exist "%ROOT%\data" mkdir "%ROOT%\data"
if not exist "%ROOT%\downloads" mkdir "%ROOT%\downloads"
if not exist "%ROOT%\downloads\multimedia" mkdir "%ROOT%\downloads\multimedia"

echo.
echo Done. Dev: scripts\dev.bat  Service: service.bat install
exit /b 0
