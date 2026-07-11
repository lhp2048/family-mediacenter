@echo off
setlocal EnableExtensions
rem Check whether a TCP port has a listener. exit /b 0 = yes, 1 = no
rem Usage: is_port_listening.bat PORT

set "PORT=%~1"
if not defined PORT exit /b 2

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "if (Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if errorlevel 1 exit /b 1
exit /b 0
