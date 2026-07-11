@echo off
setlocal EnableExtensions
rem Windows: setup venv + register logon scheduled task

call "%~dp0resolve_app_root.bat"
if errorlevel 1 exit /b 1
set "TASK_NAME=FamilyMediaCenter"
if exist "%APP_ROOT%\scripts\run_service.bat" (
  set "START_SCRIPT=%APP_ROOT%\scripts\run_service.bat"
) else (
  set "START_SCRIPT=%~dp0run_service.bat"
)
if not defined PORT set "PORT=18026"

if /i "%~1"=="--uninstall" goto :uninstall
if /i "%~1"=="--status" goto :status

if not exist "%APP_ROOT%\pyproject.toml" (
  echo ERROR: run from install directory with pyproject.toml
  exit /b 1
)

call "%~dp0setup_venv.bat"
if errorlevel 1 exit /b 1

set "PY=%APP_ROOT%\.venv\Scripts\python.exe"
"%PY%" -c "import yaml; from pathlib import Path; p=Path('config.yaml'); d=yaml.safe_load(p.read_text(encoding='utf-8')) if p.is_file() else {}; d.setdefault('server',{}); d['server']['host']='0.0.0.0'; d['server']['port']=int('%PORT%'); p.write_text(yaml.safe_dump(d, allow_unicode=True, default_flow_style=False), encoding='utf-8'); print('config.yaml server.host=0.0.0.0 port=%PORT%')"
if errorlevel 1 exit /b 1

call "%~dp0stop_service_win.bat"

schtasks /Create /TN "%TASK_NAME%" /TR "\"%START_SCRIPT%\"" /SC ONLOGON /RL LIMITED /F
if errorlevel 1 (
  echo ERROR: schtasks failed. Try run start_service_win.bat manually.
  exit /b 1
)

call "%~dp0run_service.bat"
timeout /t 3 /nobreak >nul

echo Installed scheduled task: %TASK_NAME%
echo Local:  http://127.0.0.1:%PORT%/
echo Health: http://127.0.0.1:%PORT%/health
echo Restart: service.bat restart
echo Stop:    service.bat stop
exit /b 0

:status
schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if errorlevel 1 (
  echo Task not installed: %TASK_NAME%
) else (
  schtasks /Query /TN "%TASK_NAME%" /FO LIST /V
)
if not defined PORT set "PORT=18026"
netstat -ano | findstr ":%PORT%" | findstr "LISTENING"
exit /b 0

:uninstall
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
call "%~dp0stop_service_win.bat"
echo Uninstalled: %TASK_NAME%
exit /b 0
