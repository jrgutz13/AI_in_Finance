@echo off
REM Check a video for rapid flashing (photosensitive-seizure risk).
REM Drag the video onto this file, or double-click and drag it in when asked.
REM Uses the broadcast/WCAG rule: no more than 3 flashes per second over a
REM large part of the screen. A 3-hour video takes roughly 10-20 minutes.

cd /d "%~dp0"

set "PY=python"
if exist python_cmd.txt set /p PY=<python_cmd.txt

set "VID=%~1"
if not "%VID%"=="" goto :have_video
set /p VID="Drag the video here, then press Enter: "
:have_video
set "VID=%VID:"=%"

echo Checking - this reads the whole video, please wait...
%PY% flash_check.py "%VID%"
pause
