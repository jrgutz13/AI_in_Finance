@echo off
REM Measures how fast YOUR computer renders Fractal Worlds (Mandelbulber2)
REM and estimates 10-minute, 1-hour and 3-hour render times.
cd /d "%~dp0"
set "PY=python"
if exist python_cmd.txt set /p PY=<python_cmd.txt
set "MBARG="
if exist mandelbulber_path.txt set /p MBPATH=<mandelbulber_path.txt
if defined MBPATH set "MBARG=--mandelbulber "%MBPATH%""
echo Testing 1080p (uses the GPU automatically if Mandelbulber can)...
%PY% fractal_worlds\make_fractal.py --speed-test --resolution 1920x1080 --seed 12345 %MBARG%
pause
