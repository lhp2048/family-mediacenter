@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "ROOT=%CD%"
set "JAR=%ROOT%\tvbox_spider_sidecar\build\libs\tvbox-spider-sidecar.jar"
set "PORT=9978"
if not "%~1"=="" set "PORT=%~1"

where java >nul 2>&1
if errorlevel 1 exit /b 0

if not exist "%JAR%" (
  call "%ROOT%\scripts\build_spider_sidecar.bat" >nul 2>&1
  if not exist "%JAR%" exit /b 0
)

call "%ROOT%\deploy\windows\is_port_listening.bat" %PORT%
if not errorlevel 1 exit /b 0

start "TVBox Spider Sidecar" /MIN java -jar "%JAR%" %PORT%
exit /b 0
