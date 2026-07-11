@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "ROOT=%CD%"
set "SIDECAR_DIR=%ROOT%\tvbox_spider_sidecar"
set "JAR=%SIDECAR_DIR%\build\libs\tvbox-spider-sidecar.jar"
set "PORT=9978"
if not "%~1"=="" set "PORT=%~1"

where java >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Java 11+ not found.
  exit /b 1
)

if not exist "%JAR%" (
  echo [INFO] Sidecar JAR missing, building ...
  call "%ROOT%\scripts\build_spider_sidecar.bat"
  if errorlevel 1 exit /b 1
)

echo Stopping process on port %PORT% ...
call "%ROOT%\deploy\windows\kill_port_listener.bat" %PORT% java

echo ========================================
echo TVBox Spider Sidecar
echo URL: http://127.0.0.1:%PORT%/health
echo JAR: %JAR%
echo Press Ctrl+C to stop
echo ========================================

java -jar "%JAR%" %PORT%
