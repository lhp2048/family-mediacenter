@echo off
call "%~dp0deploy\service.bat" %*
exit /b %ERRORLEVEL%
