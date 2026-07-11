@echo off
setlocal EnableExtensions
rem Install Family Media Center Cursor Skill
rem Usage: scripts\install-skill.bat [--user]

cd /d "%~dp0.."
set "PROJECT_ROOT=%CD%"
set "SKILL_NAME=family-mediacenter"
set "SOURCE=%PROJECT_ROOT%\skills\%SKILL_NAME%"
set "SCOPE=project"

:parse
if /i "%~1"=="--user" (
  set "SCOPE=user"
  shift
  goto parse
)
if /i "%~1"=="--help" goto usage
if not "%~1"=="" (
  echo Unknown arg: %~1
  goto usage
)

if not exist "%SOURCE%\SKILL.md" (
  echo ERROR: SKILL.md not found: %SOURCE%\SKILL.md
  exit /b 1
)

if /i "%SCOPE%"=="user" (
  set "TARGET=%USERPROFILE%\.cursor\skills\%SKILL_NAME%"
) else (
  for %%I in ("%PROJECT_ROOT%\..") do set "TARGET=%%~fI\.cursor\skills\%SKILL_NAME%"
)

if exist "%TARGET%" rmdir /s /q "%TARGET%"
mkdir "%TARGET%\references" 2>nul
copy /Y "%SOURCE%\SKILL.md" "%TARGET%\SKILL.md" >nul
if exist "%SOURCE%\references\api.md" copy /Y "%SOURCE%\references\api.md" "%TARGET%\references\api.md" >nul

echo Cursor Skill installed to: %TARGET%
echo Restart Cursor to pick up the skill.
exit /b 0

:usage
echo Usage: install-skill.bat [--user]
exit /b 1
