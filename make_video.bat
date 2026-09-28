@echo off
REM Double-click me to generate a video. Output lands in the "output" folder.

REM always work from the folder this script lives in
cd /d "%~dp0"

REM running straight from inside the ZIP leaves the rest of the files behind
if not exist generate.py (
    echo It looks like you are running this from INSIDE the ZIP file.
    echo Right-click PortalMachine.zip, choose "Extract All...", then run
    echo make_video.bat from the extracted PortalMachine folder.
    pause
    exit /b 1
)

REM use the Python interpreter that setup.bat picked
set "PY=python"
if exist python_cmd.txt set /p PY=<python_cmd.txt

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo ffmpeg not found. Run setup.bat first ^(then open a fresh window^).
    pause
    exit /b 1
)

%PY% -c "import moderngl" >nul 2>nul
if errorlevel 1 (
    echo The video packages are not installed yet for this Python.
    echo Run setup.bat first, then try make_video.bat again.
    pause
    exit /b 1
)

REM if a previous render was interrupted (power loss, crash), offer to finish it.
REM Labels + goto, not an if-block: inside ( ... ) a variable set by set /p is
REM read before the prompt runs, so answering "n" used to be ignored.
%PY% generate.py --resume-info >nul 2>nul
if errorlevel 1 goto :new_video
%PY% generate.py --resume-info
set "RESUME="
set /p RESUME="Finish this interrupted video? [Y/n]: "
if /i "%RESUME%"=="n" goto :skip_resume
%PY% generate.py --resume
if errorlevel 1 (
    echo.
    echo Something went wrong - see the message above.
) else (
    echo.
    echo Done! Opening the output folder...
    start output
)
pause
exit /b 0
:skip_resume
echo OK, starting a new video instead. ^(The unfinished parts stay on disk
echo until that video is resumed or you delete its _parts folder.^)
echo.

:new_video
set "DUR="
set /p DUR="Video length (examples: 45s, 10m, 3h) [press Enter for 1m]: "
if "%DUR%"=="" set DUR=1m

echo.
echo Which visual style?
echo.
echo   1   Neon Portal Tunnel        11  Data Tide (particle ocean)
echo   2   Kaleidoscope              12  Infinite Spiral Dive
echo   3   Infinite Fractal Zoom     13  Infinite Gem Rings
echo   4   Wormhole                  14  Infinite Flower
echo   5   Mandala Bloom             15  Julia Fractal Dive
echo   6   Hyperdrive                16  Hypno Polygons
echo   7   Liquid Marble             17  Vortex
echo   8   Machine Dream (Refik)     18  Galaxy Dive
echo   9   Data Wind (Refik)         19  Ripple Dive
echo   10  Machine Bloom (Refik)     20  Neon Stars
echo                                 21  Mix of everything
set "STYLE="
set /p STYLE="Choose 1-21 [press Enter for 1]: "
if "%STYLE%"=="" set STYLE=1

set "SCENEARG="
if "%STYLE%"=="1"  set "SCENEARG=--scenes neon_tunnel"
if "%STYLE%"=="2"  set "SCENEARG=--scenes kaleidoscope"
if "%STYLE%"=="3"  set "SCENEARG=--scenes fractal_zoom"
if "%STYLE%"=="4"  set "SCENEARG=--scenes wormhole"
if "%STYLE%"=="5"  set "SCENEARG=--scenes mandala"
if "%STYLE%"=="6"  set "SCENEARG=--scenes hyperdrive"
if "%STYLE%"=="7"  set "SCENEARG=--scenes liquid"
if "%STYLE%"=="8"  set "SCENEARG=--scenes machine_dream"
if "%STYLE%"=="9"  set "SCENEARG=--scenes data_wind"
if "%STYLE%"=="10" set "SCENEARG=--scenes machine_bloom"
if "%STYLE%"=="11" set "SCENEARG=--scenes data_tide"
if "%STYLE%"=="12" set "SCENEARG=--scenes spiral_dive"
if "%STYLE%"=="13" set "SCENEARG=--scenes droste_zoom"
if "%STYLE%"=="14" set "SCENEARG=--scenes infinite_flower"
if "%STYLE%"=="15" set "SCENEARG=--scenes julia_dive"
if "%STYLE%"=="16" set "SCENEARG=--scenes nested_squares"
if "%STYLE%"=="17" set "SCENEARG=--scenes vortex"
if "%STYLE%"=="18" set "SCENEARG=--scenes galaxy_dive"
if "%STYLE%"=="19" set "SCENEARG=--scenes ripple_dive"
if "%STYLE%"=="20" set "SCENEARG=--scenes neon_stars"

echo.
echo Resolution?
echo   1  1080p  (1920x1080 - fast, smaller files)
echo   2  1440p  (2560x1440)
echo   3  4K     (3840x2160 - sharpest, ~4x the render time of 1080p)
set "RES="
set /p RES="Choose 1-3 [press Enter for 1]: "
set "RESARG=--resolution 1920x1080"
if "%RES%"=="2" set "RESARG=--resolution 2560x1440"
if "%RES%"=="3" set "RESARG=--resolution 3840x2160"

echo.
set "MUSIC="
set /p MUSIC="Music file to loop underneath (drag the file here, or Enter for silent): "

REM strip quotes that drag-and-drop adds (only when something was entered -
REM running the replacement on an empty variable crashes the script)
if defined MUSIC set "MUSIC=%MUSIC:"=%"

if "%MUSIC%"=="" (
    %PY% generate.py --duration %DUR% %RESARG% %SCENEARG%
) else (
    %PY% generate.py --duration %DUR% %RESARG% %SCENEARG% --audio "%MUSIC%"
)

if errorlevel 1 (
    echo.
    echo Something went wrong - see the message above.
) else (
    echo.
    echo Done! Opening the output folder...
    start output
)
pause
