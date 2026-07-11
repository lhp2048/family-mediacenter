@echo off
call "%~dp0deploy\install.bat" %*
exit /b %ERRORLEVEL%
