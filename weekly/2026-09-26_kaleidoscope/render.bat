@echo off
REM Weekly video: 3D Kaleidoscope. Double-click to render the full video.
REM Needs Blender 4.5 LTS or newer (free): https://www.blender.org/download/lts/
REM Prompts use labels + goto, not if-blocks: inside ( ... ) a variable set
REM by set /p is read before the prompt runs.

cd /d "%~dp0..\.."
set "SCENE=weekly\2026-09-26_kaleidoscope\kaleidoscope.py"
set "DRIVER=weekly\common\render_driver.py"

set "PY=python"
if exist python_cmd.txt set /p PY=<python_cmd.txt

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo ffmpeg not found. Run setup.bat in the PortalMachine folder first.
    pause
    exit /b 1
)

%PY% %DRIVER% --resume-info >nul 2>nul
if errorlevel 1 goto :new_render
%PY% %DRIVER% --resume-info
set "RESUME="
set /p RESUME="Finish this interrupted render? [Y/n]: "
if /i "%RESUME%"=="n" goto :new_render
%PY% %DRIVER% --resume
goto :finished

:new_render
set "DUR="
set /p DUR="Video length (examples: 10m, 1h, 3h) [press Enter for 3h]: "
if "%DUR%"=="" set DUR=3h

echo.
echo Resolution?
echo   1  1080p fast   - rendered at 1600x900 and upscaled; a touch softer,
echo                     about 30%% faster (recommended)
echo   2  1080p sharp  - rendered at full 1920x1080
set "RES="
set /p RES="Choose 1-2 [press Enter for 1]: "
set "RESARG=--resolution 1920x1080 --render-scale 0.8333"
if "%RES%"=="2" set "RESARG=--resolution 1920x1080"

echo.
set "LOOP="
set /p LOOP="Seamless loop length - only this much is rendered, then repeated [press Enter for 10m]: "
if "%LOOP%"=="" set LOOP=10m
REM the approved look: photoreal gems, gold and stone, neon colors, strong glow
set "ENGARG=--engine cycles --style real --glow strong --loop %LOOP%"

echo.
set "MUSIC="
set /p MUSIC="Music file to loop underneath (drag the file here, or Enter for silent): "
if defined MUSIC set "MUSIC=%MUSIC:"=%"

REM seed 1 = the same kaleidoscope journey as the approved samples
if "%MUSIC%"=="" goto :silent
%PY% %DRIVER% --scene %SCENE% --seed 1 --fps 24 --duration %DUR% %RESARG% %ENGARG% --audio "%MUSIC%"
goto :finished
:silent
%PY% %DRIVER% --scene %SCENE% --seed 1 --fps 24 --duration %DUR% %RESARG% %ENGARG%

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
