@echo off
REM Starts Wan2GP (installed by install_wan.bat). It opens in your browser.
setlocal
set "DEST=C:\Wan2GP"
if exist "%~dp0wan_path.txt" set /p DEST=<"%~dp0wan_path.txt"
if not exist "%DEST%\scripts\run.bat" goto :missing
echo Starting Wan2GP from %DEST% ... (leave this window open while you use it)
call "%DEST%\scripts\run.bat"
exit /b 0

:missing
echo Wan2GP was not found in %DEST%.
echo Double-click install_wan.bat first.
pause
exit /b 1
