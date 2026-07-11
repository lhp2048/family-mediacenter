@echo off
setlocal EnableExtensions
rem Safely stop a process listening on an exact TCP port.
rem Usage: kill_port_listener.bat PORT [process_name]
rem   process_name: optional filter without .exe (e.g. python, java)

set "PORT=%~1"
set "PROC_FILTER=%~2"
if not defined PORT (
  echo ERROR: kill_port_listener.bat requires PORT
  exit /b 1
)

if defined PROC_FILTER (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$port = %PORT%; $filter = '%PROC_FILTER%';" ^
    "$conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue;" ^
    "foreach ($c in $conns) {" ^
    "  $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue;" ^
    "  if (-not $p) { continue };" ^
    "  if ($p.Name -notlike ('*' + $filter + '*')) { Write-Host ('Skipping ' + $p.Name + ' (PID ' + $p.Id + ') on port ' + $port); continue };" ^
    "  Write-Host ('Stopping ' + $p.Name + ' (PID ' + $p.Id + ') on port ' + $port);" ^
    "  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue" ^
    "}"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$port = %PORT%;" ^
    "$conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue;" ^
    "foreach ($c in $conns) {" ^
    "  $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue;" ^
    "  if (-not $p) { continue };" ^
    "  Write-Host ('Stopping ' + $p.Name + ' (PID ' + $p.Id + ') on port ' + $port);" ^
    "  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue" ^
    "}"
)

exit /b 0
