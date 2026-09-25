@echo off
REM Clip Stitcher: turns a folder of short clips and/or images (for example
REM from an AI video generator) into one long video with smooth crossfades.
REM
REM Prompts are handled with labels + goto rather than if-blocks: inside
REM ( ... ) a variable set by set /p is read before the prompt runs.

cd /d "%~dp0"

if not exist stitcher\stitch.py (
    echo It looks like you are running this from INSIDE the ZIP file.
    echo Right-click PortalMachine.zip, choose "Extract All...", then run
    echo stitch_clips.bat from the extracted PortalMachine folder.
    pause
    exit /b 1
)

set "PY=python"
if exist python_cmd.txt set /p PY=<python_cmd.txt

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo ffmpeg not found. Run setup.bat first ^(then open a fresh window^).
    pause
    exit /b 1
)

REM ---- offer to finish an interrupted stitch ------------------------------
%PY% stitcher\stitch.py --resume-info >nul 2>nul
if errorlevel 1 goto :new_stitch
%PY% stitcher\stitch.py --resume-info
set "RESUME="
set /p RESUME="Finish this interrupted video? [Y/n]: "
if /i "%RESUME%"=="n" goto :skip_resume
%PY% stitcher\stitch.py --resume
goto :finished
:skip_resume
echo OK, starting a new video instead.
echo.

:new_stitch
set "SRC="
set /p SRC="Drag the FOLDER with your clips/images here, then press Enter: "
if defined SRC set "SRC=%SRC:"=%"
if not defined SRC (
    echo No folder given.
    pause
    exit /b 1
)
REM a trailing backslash (e.g. D:\) would escape the closing quote below
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"

set "DUR="
set /p DUR="Video length (examples: 30m, 1h, 3h) [press Enter for 1h]: "
if "%DUR%"=="" set DUR=1h

echo.
echo Resolution?
echo   1  1080p
echo   2  1440p
echo   3  4K
set "RES="
set /p RES="Choose 1-3 [press Enter for 1]: "
set "RESARG=--resolution 1920x1080"
if "%RES%"=="2" set "RESARG=--resolution 2560x1440"
if "%RES%"=="3" set "RESARG=--resolution 3840x2160"

echo.
set "FADE="
set /p FADE="Crossfade seconds between shots [press Enter for 2]: "
if "%FADE%"=="" set FADE=2

set "STILL="
set /p STILL="Seconds to show each still image [press Enter for 12]: "
if "%STILL%"=="" set STILL=12

echo.
echo Slow motion makes every clip last twice as long with smooth invented
echo in-between frames - dreamier, and you need half as many clips.
echo It makes rendering MUCH slower.
set "SLOW="
set /p SLOW="Use 2x slow motion on video clips? [y/N]: "
set "SLOWARG="
if /i "%SLOW%"=="y" set "SLOWARG=--slow 2"

echo.
set "MUSIC="
set /p MUSIC="Music file to loop underneath (drag the file here, or Enter for silent): "
if defined MUSIC set "MUSIC=%MUSIC:"=%"

if "%MUSIC%"=="" goto :silent
%PY% stitcher\stitch.py "%SRC%" --duration %DUR% %RESARG% --crossfade %FADE% --still-seconds %STILL% %SLOWARG% --audio "%MUSIC%"
goto :finished
:silent
%PY% stitcher\stitch.py "%SRC%" --duration %DUR% %RESARG% --crossfade %FADE% --still-seconds %STILL% %SLOWARG%

:finished
if errorlevel 1 (
    echo.
    echo Something went wrong - see the message above.
) else (
    echo.
    echo Done! Opening the output folder...
    start output
)
pause
