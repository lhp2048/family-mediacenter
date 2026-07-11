@echo off
setlocal EnableExtensions

rem Pack dist into zip + validate manifest + write package-index
rem Usage: scripts\pack.bat

set "SCRIPT_DIR=%~dp0"
set "ROOT=%SCRIPT_DIR%.."
set "DIST=%ROOT%\dist"
set "OUT_DIR=%ROOT%\dist_out"

if not exist "%DIST%\app\main.py" (
  echo ERROR: %DIST%\app\main.py not found. Run scripts\build.bat first.
  exit /b 1
)

set "PYTHON=python"
if exist "%ROOT%\.venv\Scripts\python.exe" set "PYTHON=%ROOT%\.venv\Scripts\python.exe"

"%PYTHON%" "%SCRIPT_DIR%sync_skill_manifest.py" --manifest "%ROOT%\family-product.json" --dist "%DIST%"
if errorlevel 1 exit /b 1

"%PYTHON%" "%SCRIPT_DIR%bump_manifest_version.py" --manifest "%ROOT%\family-product.json" --dist "%DIST%"
if errorlevel 1 exit /b 1

"%PYTHON%" "%SCRIPT_DIR%validate_manifest.py" "%ROOT%\family-product.json" --dist "%DIST%"
if errorlevel 1 exit /b 1

set "ZIP_NAME=family_mediacenter.zip"
for /f "usebackq delims=" %%v in (`"%PYTHON%" "%SCRIPT_DIR%read_manifest_field.py" "%ROOT%\family-product.json" zipNameHint family_mediacenter.zip`) do set "ZIP_NAME=%%v"

set "ZIP_FILE=%OUT_DIR%\%ZIP_NAME%"
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"
if exist "%ZIP_FILE%" del /f /q "%ZIP_FILE%"

"%PYTHON%" "%SCRIPT_DIR%make_zip.py" "%DIST%" "%ZIP_FILE%"
if errorlevel 1 exit /b 1

"%PYTHON%" "%SCRIPT_DIR%write_package_info.py" --manifest "%ROOT%\family-product.json" --zip "%ZIP_FILE%" --dist "%DIST%"
if errorlevel 1 exit /b 1

echo.
echo Packed: %ZIP_FILE%

endlocal
