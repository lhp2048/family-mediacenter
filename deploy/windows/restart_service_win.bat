@echo off
setlocal EnableExtensions
rem Restart Family Media Center on Windows

cd /d "%~dp0.."
if not defined PORT set "PORT=18026"

call "%~dp0stop_service_win.bat"
call "%~dp0start_service_win.bat"
exit /b %ERRORLEVEL%
