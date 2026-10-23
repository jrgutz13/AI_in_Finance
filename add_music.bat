@echo off
REM Add music to a finished video, without re-rendering it (takes minutes,
REM even for 3 hours). Drag the video onto this file - or the video and the
REM music together - or double-click and drag them in when asked.
REM The music repeats for the whole video and fades out at the end.
REM Saved next to the video with "_music" added to the name.
REM Prompts use labels + goto, not if-blocks (set /p inside ( ... ) is read
REM before the prompt runs).

cd /d "%~dp0"

set "PY=python"
if exist python_cmd.txt set /p PY=<python_cmd.txt

set "F1=%~1"
set "F2=%~2"
if not "%F1%"=="" goto :have_first
set /p F1="Drag the VIDEO here, then press Enter: "
:have_first
if not "%F2%"=="" goto :have_both
set /p F2="Drag the MUSIC file (or a folder of songs) here, then press Enter: "
:have_both
set "F1=%F1:"=%"
set "F2=%F2:"=%"

%PY% add_music.py "%F1%" "%F2%"
if errorlevel 1 goto :failed
echo.
echo Done! The new video (with "_music" in its name) is next to the original.
pause
exit /b 0

:failed
echo.
echo Something went wrong - see the message above.
pause
exit /b 1
