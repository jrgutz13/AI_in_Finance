@echo off
REM Reverse a finished video. Drag the .mp4 onto this file, or double-click
REM it and paste the path when asked. Output is saved next to the original
REM with "_reversed" added to the name.

cd /d "%~dp0"

set "PY=python"
if exist python_cmd.txt set /p PY=<python_cmd.txt

set "VID=%~1"
if "%VID%"=="" (
    set /p VID="Drag the video here, or paste its path, then press Enter: "
)
if defined VID set "VID=%VID:"=%"

if "%VID%"=="" (
    echo No file given.
    pause
    exit /b 1
)

%PY% reverse_video.py "%VID%"

if errorlevel 1 (
    echo.
    echo Something went wrong - see the message above.
) else (
    echo.
    echo Done! The reversed video is in the same folder as the original.
)
pause
