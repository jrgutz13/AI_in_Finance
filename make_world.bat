@echo off
REM Blender Worlds: photoreal-style bioluminescent alien landscapes.
REM Needs Blender installed (free): https://www.blender.org/download/lts/
REM
REM Note on structure: in batch files a variable set inside a ( ... ) block
REM is read BEFORE the block runs, so every prompt whose answer is checked
REM right away uses labels + goto instead of if-blocks.

cd /d "%~dp0"

if not exist blender_worlds\make_world.py (
    echo It looks like you are running this from INSIDE the ZIP file.
    echo Right-click PortalMachine.zip, choose "Extract All...", then run
    echo make_world.bat from the extracted PortalMachine folder.
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

REM ---- offer to finish an interrupted render ------------------------------
%PY% blender_worlds\make_world.py --resume-info >nul 2>nul
if errorlevel 1 goto :new_video
%PY% blender_worlds\make_world.py --resume-info
set "RESUME="
set /p RESUME="Finish this interrupted world video? [Y/n]: "
if /i "%RESUME%"=="n" goto :skip_resume
%PY% blender_worlds\make_world.py --resume
goto :finished
:skip_resume
echo OK, starting a new world video instead.
echo.

:new_video
set "DUR="
set /p DUR="Video length (examples: 30s, 10m, 3h) [press Enter for 1m]: "
if "%DUR%"=="" set DUR=1m

echo.
echo Resolution?
echo   1  1080p  (recommended)
echo   2  1440p
echo   3  4K     (very slow for worlds)
set "RES="
set /p RES="Choose 1-3 [press Enter for 1]: "
set "RESARG=--resolution 1920x1080"
if "%RES%"=="2" set "RESARG=--resolution 2560x1440"
if "%RES%"=="3" set "RESARG=--resolution 3840x2160"

echo.
echo Quality?
echo   1  draft     (fastest - good for testing)
echo   2  standard  (recommended)
echo   3  high      (cleanest, slowest)
set "Q="
set /p Q="Choose 1-3 [press Enter for 2]: "
set "QARG=--quality standard"
if "%Q%"=="1" set "QARG=--quality draft"
if "%Q%"=="3" set "QARG=--quality high"

REM pick the seed here so the preview and the video show the same world
set "SEED=%RANDOM%%RANDOM%"

REM ---- optional preview picture ------------------------------------------
echo.
set "PREV="
set /p PREV="Render a quick preview picture of this world first? [Y/n]: "
if /i "%PREV%"=="n" goto :ask_music
echo Rendering preview - the first one takes a minute while Blender warms up...
%PY% blender_worlds\make_world.py --preview 45 --seed %SEED% %RESARG% %QARG%
if errorlevel 1 goto :finished
start "" "output\world_%SEED%_t45.png"
set "GO="
set /p GO="Render the video of this world [Y], or stop and try another [n]: "
if /i not "%GO%"=="n" goto :ask_music
echo Run make_world.bat again for a new random world.
pause
exit /b 0

:ask_music
echo.
set "MUSIC="
set /p MUSIC="Music file to loop underneath (drag the file here, or Enter for silent): "
if defined MUSIC set "MUSIC=%MUSIC:"=%"

if "%MUSIC%"=="" goto :silent
%PY% blender_worlds\make_world.py --duration %DUR% --seed %SEED% %RESARG% %QARG% --audio "%MUSIC%"
goto :finished
:silent
%PY% blender_worlds\make_world.py --duration %DUR% --seed %SEED% %RESARG% %QARG%

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
