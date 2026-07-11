@echo off
setlocal EnableExtensions
cd /d "%~dp0..\tvbox_spider_sidecar"

where java >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Java 11+ not found. Install JDK and add to PATH.
  exit /b 1
)

where gradle >nul 2>&1
if errorlevel 1 (
  if exist "%TEMP%\gradle-8.5\bin\gradle.bat" (
    set "GRADLE=%TEMP%\gradle-8.5\bin\gradle.bat"
  ) else (
    echo [ERROR] Gradle not found. Install Gradle 8+ or run once with network to cache %TEMP%\gradle-8.5
    exit /b 1
  )
) else (
  set "GRADLE=gradle"
)

echo Building tvbox-spider-sidecar ...
"%GRADLE%" shadowJar --no-daemon
if errorlevel 1 exit /b 1

echo.
echo Output: build\libs\tvbox-spider-sidecar.jar
exit /b 0
