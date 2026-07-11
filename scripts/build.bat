@echo off
setlocal EnableExtensions

rem Assemble family_mediacenter dist for zip deploy
rem Usage: scripts\build.bat

set "SCRIPT_DIR=%~dp0"
set "ROOT=%SCRIPT_DIR%.."
set "DIST=%ROOT%\dist"

cd /d "%ROOT%"

set "PYTHON=python"
if exist "%ROOT%\.venv\Scripts\python.exe" set "PYTHON=%ROOT%\.venv\Scripts\python.exe"

if exist "%DIST%" rmdir /s /q "%DIST%"
mkdir "%DIST%"
mkdir "%DIST%\scripts"
mkdir "%DIST%\scripts\lib"
mkdir "%DIST%\data"
mkdir "%DIST%\downloads"
mkdir "%DIST%\downloads\multimedia"
mkdir "%DIST%\logs"

xcopy /E /I /Y "%ROOT%\app" "%DIST%\app\" >nul
for /d /r "%DIST%\app" %%D in (__pycache__) do @if exist "%%D" rmdir /s /q "%%D" 2>nul

xcopy /E /I /Y "%ROOT%\skills" "%DIST%\skills\" >nul
if exist "%ROOT%\mcp_server" xcopy /E /I /Y "%ROOT%\mcp_server" "%DIST%\mcp_server\" >nul
for /d /r "%DIST%\mcp_server" %%D in (__pycache__) do @if exist "%%D" rmdir /s /q "%%D" 2>nul

copy /Y "%ROOT%\config.yaml" "%DIST%\config.yaml" >nul
copy /Y "%ROOT%\pyproject.toml" "%DIST%\pyproject.toml" >nul
if exist "%ROOT%\docker-compose.yml" copy /Y "%ROOT%\docker-compose.yml" "%DIST%\docker-compose.yml" >nul
copy /Y "%ROOT%\family-product.json" "%DIST%\family-product.json" >nul
copy /Y "%ROOT%\deploy\INSTALL.txt" "%DIST%\INSTALL.txt" >nul

for %%F in (service install) do (
  if exist "%ROOT%\deploy\%%F.bat" copy /Y "%ROOT%\deploy\%%F.bat" "%DIST%\%%F.bat" >nul
  if exist "%ROOT%\deploy\%%F.sh" copy /Y "%ROOT%\deploy\%%F.sh" "%DIST%\%%F.sh" >nul
)

copy /Y "%ROOT%\deploy\windows\*.bat" "%DIST%\scripts\" >nul
copy /Y "%ROOT%\deploy\linux\*.sh" "%DIST%\scripts\" >nul
copy /Y "%ROOT%\deploy\mac\*.sh" "%DIST%\scripts\" >nul
copy /Y "%ROOT%\deploy\lib\*.sh" "%DIST%\scripts\lib\" >nul

for %%F in (install-workbuddy-skill install-skill) do (
  if exist "%ROOT%\scripts\%%F.sh" copy /Y "%ROOT%\scripts\%%F.sh" "%DIST%\scripts\%%F.sh" >nul
  if exist "%ROOT%\scripts\%%F.bat" copy /Y "%ROOT%\scripts\%%F.bat" "%DIST%\scripts\%%F.bat" >nul
  if exist "%ROOT%\scripts\%%F.ps1" copy /Y "%ROOT%\scripts\%%F.ps1" "%DIST%\scripts\%%F.ps1" >nul
)

"%PYTHON%" "%SCRIPT_DIR%normalize_shell.py" "%ROOT%\deploy" "%DIST%"
if errorlevel 1 exit /b 1

"%PYTHON%" "%SCRIPT_DIR%validate_manifest.py" "%ROOT%\family-product.json" --dist "%DIST%"
if errorlevel 1 exit /b 1

echo.
echo Done: %DIST%
echo Pack:  scripts\pack.bat
echo Deploy: see dist\INSTALL.txt

endlocal
