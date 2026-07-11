@echo off
setlocal EnableExtensions
rem Service maintenance (single entry): install | start | stop | restart | status | uninstall

cd /d "%~dp0"

if exist "%~dp0scripts\install_service_win.bat" (
  set "WIN_DIR=%~dp0scripts"
) else if exist "%~dp0windows\install_service_win.bat" (
  set "WIN_DIR=%~dp0windows"
) else (
  echo ERROR: install_service_win.bat not found
  exit /b 1
)

if "%~1"=="" goto :usage

set "ACTION=%~1"
shift

if /i "%ACTION%"=="install" (
  call "%WIN_DIR%\install_service_win.bat" %*
  exit /b %ERRORLEVEL%
)
if /i "%ACTION%"=="start" (
  call "%WIN_DIR%\start_service_win.bat" %*
  exit /b %ERRORLEVEL%
)
if /i "%ACTION%"=="stop" (
  call "%WIN_DIR%\stop_service_win.bat" %*
  exit /b %ERRORLEVEL%
)
if /i "%ACTION%"=="restart" (
  call "%WIN_DIR%\restart_service_win.bat" %*
  exit /b %ERRORLEVEL%
)
if /i "%ACTION%"=="status" (
  call "%WIN_DIR%\install_service_win.bat" --status %*
  exit /b %ERRORLEVEL%
)
if /i "%ACTION%"=="uninstall" (
  call "%WIN_DIR%\install_service_win.bat" --uninstall %*
  exit /b %ERRORLEVEL%
)

echo Unknown action: %ACTION%
goto :usage

:usage
echo Usage: service.bat install^|start^|stop^|restart^|status^|uninstall
exit /b 1
