@echo off
setlocal EnableExtensions
rem Install Family Media Center WorkBuddy Skill
rem Usage: scripts\install-workbuddy-skill.bat [BaseUrl]

set "BASE_URL=%~1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-workbuddy-skill.ps1" %*
exit /b %ERRORLEVEL%
