@echo off
REM How fast does YOUR computer render this week's video? Takes a few minutes.
cd /d "%~dp0..\.."
set "PY=python"
if exist python_cmd.txt set /p PY=<python_cmd.txt
echo Testing photoreal 1080p fast at 24 fps. The first two frames include Blender
echo warming up and are left out of the estimate.
echo.
%PY% weekly\common\render_driver.py --scene weekly\2026-09-26_kaleidoscope\kaleidoscope.py --seed 1 --fps 24 --resolution 1920x1080 --render-scale 0.8333 --engine cycles --style real --loop 10m --speed-test
echo.
echo The 10-minute line is how long the full 3-hour video takes (it is a 10-minute
echo loop played 18 times).
pause
