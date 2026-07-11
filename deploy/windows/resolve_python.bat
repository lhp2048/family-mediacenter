@echo off
setlocal EnableExtensions
rem Resolve Python >= 3.10 for Family Media Center venv
rem Sets PY_BOOTSTRAP to command prefix, e.g. "py -3.12" or "python"

set "PY_BOOTSTRAP="
set "RESOLVED_PYTHON_VERSION="

if defined PYTHON_BIN (
  "%PYTHON_BIN%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
  if not errorlevel 1 (
    set "PY_BOOTSTRAP=%PYTHON_BIN%"
    for /f "delims=" %%v in ('"%PYTHON_BIN%" --version 2^>^&1') do set "RESOLVED_PYTHON_VERSION=%%v"
    goto :done
  )
  echo ERROR: PYTHON_BIN=%PYTHON_BIN% needs Python 3.10+
  exit /b 1
)

where py >nul 2>&1
if not errorlevel 1 (
  for %%V in (3.13 3.12 3.11 3.10) do (
    if not defined PY_BOOTSTRAP (
      py -%%V -c "import sys" >nul 2>&1
      if not errorlevel 1 set "PY_BOOTSTRAP=py -%%V"
    )
  )
)

if not defined PY_BOOTSTRAP (
  where python >nul 2>&1
  if not errorlevel 1 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY_BOOTSTRAP=python"
  )
)

if not defined PY_BOOTSTRAP (
  echo ERROR: Python 3.10+ required. Install from python.org or: py -3.12
  exit /b 1
)

for /f "delims=" %%v in ('%PY_BOOTSTRAP% --version 2^>^&1') do set "RESOLVED_PYTHON_VERSION=%%v"

:done
echo Using: %PY_BOOTSTRAP% (%RESOLVED_PYTHON_VERSION%)
endlocal & set "PY_BOOTSTRAP=%PY_BOOTSTRAP%" & set "RESOLVED_PYTHON_VERSION=%RESOLVED_PYTHON_VERSION%"
exit /b 0
