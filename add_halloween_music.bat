@echo off
REM Adds the Halloween songs (the "Halloween" folder inside "output") to the
REM Halloween video, in this order, looping the playlist for the whole video:
REM   Skeleton Dance, Paranormal Things, Creepy Atonal, Apprehensive at Best,
REM   Dark Walk, Spookster, Creepy Photography, then the rest alphabetically.
REM Takes minutes: the picture is copied as-is, not re-rendered.
REM Prompts use labels + goto, not if-blocks.

cd /d "%~dp0"

set "PY=python"
if exist python_cmd.txt set /p PY=<python_cmd.txt

set "SONGS=output\Halloween"
if exist "%SONGS%\" goto :have_songs
echo Couldn't find the folder "%SONGS%".
set /p SONGS="Drag the folder of Halloween songs here, then press Enter: "
set "SONGS=%SONGS:"=%"
:have_songs

set "VID=%~1"
if not "%VID%"=="" goto :have_video
set /p VID="Drag the Halloween VIDEO (from the output folder) here, then press Enter: "
:have_video
set "VID=%VID:"=%"

%PY% add_music.py "%VID%" "%SONGS%" --confirm --order "Skeleton Dance;Paranormal Things;Creepy Atonal;Apprehensive at Best;Dark Walk;Spookster;Creepy Photography"
if errorlevel 1 goto :failed
echo.
echo Done! The new video (with "_music" in its name) is next to the original.
pause
exit /b 0

:failed
echo.
echo Stopped - see the message above.
pause
exit /b 1
