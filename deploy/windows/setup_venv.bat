@echo off
setlocal EnableExtensions
rem Create .venv in Family Media Center install directory (Python 3.10+)

call "%~dp0resolve_app_root.bat"
if errorlevel 1 exit /b 1

call "%~dp0resolve_python.bat"
if errorlevel 1 exit /b 1

if exist "%APP_ROOT%\.venv\Scripts\python.exe" (
  "%APP_ROOT%\.venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
  if errorlevel 1 (
    echo Removing old .venv - Python version too old
    rmdir /s /q "%APP_ROOT%\.venv"
  )
)

if not exist "%APP_ROOT%\.venv\Scripts\python.exe" (
  echo Creating venv...
  %PY_BOOTSTRAP% -m venv "%APP_ROOT%\.venv"
  if errorlevel 1 exit /b 1
)

set "PY=%APP_ROOT%\.venv\Scripts\python.exe"
"%PY%" -m pip install -U pip setuptools wheel -q
"%PY%" -m pip install -e "%APP_ROOT%" -q
"%PY%" -m pip install yt-dlp -q

"%PY%" -c "import uvicorn; from app.main import app" >nul 2>&1
if errorlevel 1 (
  echo ERROR: verify imports failed
  exit /b 1
)

if not exist "%APP_ROOT%\logs" mkdir "%APP_ROOT%\logs"
if not exist "%APP_ROOT%\data" mkdir "%APP_ROOT%\data"
if not exist "%APP_ROOT%\downloads" mkdir "%APP_ROOT%\downloads"
if not exist "%APP_ROOT%\downloads\multimedia" mkdir "%APP_ROOT%\downloads\multimedia"

echo Done: %APP_ROOT%\.venv
exit /b 0
