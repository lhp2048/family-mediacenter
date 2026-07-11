@echo off
setlocal EnableExtensions
rem Stop Family Media Center on PORT (default 18026)

if not defined PORT set "PORT=18026"

echo Stopping listeners on port %PORT% ...
call "%~dp0kill_port_listener.bat" %PORT% python
echo Done.
exit /b 0
