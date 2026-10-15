@echo off
REM One-click helper: downloads Wan2GP (free AI video app for Wan 2.2) and
REM starts its own installer. See WAN_2.2_GUIDE.txt for how to use it.
REM Prompts use labels + goto, not if-blocks (set /p inside ( ... ) is read
REM before the prompt runs).
setlocal
echo ============================================================
echo   Wan2GP installer helper  (AI video clips with Wan 2.2)
echo ============================================================
echo.
echo This downloads Wan2GP and runs its installer. It needs an internet
echo connection and about 60 GB of free disk space, and takes a while
echo (Python, PyTorch and the AI models are big downloads).
echo.
set "DEST="
set /p DEST="Install folder [press Enter for C:\Wan2GP]: "
if "%DEST%"=="" set "DEST=C:\Wan2GP"
set "DEST=%DEST:"=%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_wan.ps1" -Dest "%DEST%"
if errorlevel 2 goto :nospace
if errorlevel 1 goto :failed

REM remember where it is, for start_wan.bat
>"%~dp0wan_path.txt" echo(%DEST%

echo.
echo ------------------------------------------------------------
echo  Wan2GP's own installer starts now. When it asks:
echo    - choose  1  (Automatic Install)
echo    - if it offers to install Git or Python, answer  Y  (yes)
echo  When it says the install is finished, choose  3  (Exit).
echo ------------------------------------------------------------
pause
call "%DEST%\scripts\install.bat"

echo.
echo ============================================================
echo  Done. To start Wan2GP from now on, double-click  start_wan.bat
echo  (in this folder). It opens in your web browser.
echo  Then follow WAN_2.2_GUIDE.txt, section 3 (settings for your card).
echo ============================================================
pause
exit /b 0

:nospace
echo.
echo Not enough free space. Free up about 60 GB, or run this again and
echo choose a folder on another drive (for example D:\Wan2GP).
pause
exit /b 1

:failed
echo.
echo The download failed - see the message above. Check your internet
echo connection and try again.
pause
exit /b 1
