@echo off
rem Sets APP_ROOT to directory containing pyproject.toml (dist root or repo root)
cd /d "%~dp0.."
if exist "pyproject.toml" (
  set "APP_ROOT=%CD%"
) else (
  cd ..
  if not exist "pyproject.toml" (
    echo ERROR: pyproject.toml not found
    exit /b 1
  )
  set "APP_ROOT=%CD%"
)
exit /b 0
