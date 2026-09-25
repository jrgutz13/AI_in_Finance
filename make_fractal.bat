@echo off
REM Fractal Worlds: an endless flight over a fractal alien landscape,
REM rendered by Mandelbulber2 (free): https://github.com/buddhi1980/mandelbulber2/releases
REM
REM Prompts use labels + goto rather than if-blocks: inside ( ... ) a
REM variable set by set /p is read before the prompt runs.

cd /d "%~dp0"

if not exist fractal_worlds\make_fractal.py (
    echo It looks like you are running this from INSIDE the ZIP file.
    echo Right-click PortalMachine.zip, choose "Extract All...", then run
    echo make_fractal.bat from the extracted PortalMachine folder.
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

REM ---- remember where Mandelbulber lives, asking once if it can't be found --
set "MBARG="
if exist mandelbulber_path.txt set /p MBPATH=<mandelbulber_path.txt
if defined MBPATH set "MBARG=--mandelbulber "%MBPATH%""
%PY% -c "import sys; sys.path.insert(0,'fractal_worlds'); import mb; sys.exit(0 if mb.find_mandelbulber(sys.argv[1] if len(sys.argv)>1 else None) else 1)" "%MBPATH%"
if not errorlevel 1 goto :have_mb
echo Mandelbulber2 was not found.
echo Download it free from https://github.com/buddhi1980/mandelbulber2/releases
echo and extract it anywhere. Then drag mandelbulber2.exe into this window.
set "MBPATH="
set /p MBPATH="mandelbulber2.exe location: "
if defined MBPATH set "MBPATH=%MBPATH:"=%"
if not defined MBPATH exit /b 1
echo %MBPATH%> mandelbulber_path.txt
set "MBARG=--mandelbulber "%MBPATH%""
:have_mb

REM ---- offer to finish an interrupted render ------------------------------
%PY% fractal_worlds\make_fractal.py --resume-info %MBARG% >nul 2>nul
if errorlevel 1 goto :new_video
%PY% fractal_worlds\make_fractal.py --resume-info %MBARG%
set "RESUME="
set /p RESUME="Finish this interrupted fractal video? [Y/n]: "
if /i "%RESUME%"=="n" goto :skip_resume
%PY% fractal_worlds\make_fractal.py --resume %MBARG%
goto :finished
:skip_resume
echo OK, starting a new video instead.
echo.

:new_video
set "DUR="
set /p DUR="Video length (examples: 30s, 10m, 3h) [press Enter for 1m]: "
if "%DUR%"=="" set DUR=1m

echo.
echo Resolution?
echo   1  1080p  (recommended)
echo   2  1440p
echo   3  4K     (very slow)
set "RES="
set /p RES="Choose 1-3 [press Enter for 1]: "
set "RESARG=--resolution 1920x1080"
if "%RES%"=="2" set "RESARG=--resolution 2560x1440"
if "%RES%"=="3" set "RESARG=--resolution 3840x2160"

REM pick the seed here so the preview and the video show the same journey
set "SEED=1%RANDOM%%RANDOM%"

echo.
set "PREV="
set /p PREV="Render a preview picture of this journey first? [Y/n]: "
if /i "%PREV%"=="n" goto :ask_music
%PY% fractal_worlds\make_fractal.py --preview 30 --seed %SEED% %RESARG% %MBARG%
if errorlevel 1 goto :finished
start "" "output\fractal_%SEED%_t30.png"
set "GO="
set /p GO="Render the video of this journey [Y], or stop and try another [n]: "
if /i not "%GO%"=="n" goto :ask_music
echo Run make_fractal.bat again for a new random journey.
pause
exit /b 0

:ask_music
echo.
set "MUSIC="
set /p MUSIC="Music file to loop underneath (drag the file here, or Enter for silent): "
if defined MUSIC set "MUSIC=%MUSIC:"=%"

if "%MUSIC%"=="" goto :silent
%PY% fractal_worlds\make_fractal.py --duration %DUR% --seed %SEED% %RESARG% %MBARG% --audio "%MUSIC%"
goto :finished
:silent
%PY% fractal_worlds\make_fractal.py --duration %DUR% --seed %SEED% %RESARG% %MBARG%

:finished
if errorlevel 1 (
    echo.
    echo Something went wrong - see the message above.
) else (
    echo.
    echo Done! Opening the output folder...
    echo Remember to paste the _credits.txt text into your video description.
    start output
)
pause
