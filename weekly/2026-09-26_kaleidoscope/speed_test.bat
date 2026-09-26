@echo off
REM How fast does YOUR computer render this week's video? Takes a few minutes.
cd /d "%~dp0..\.."
set "PY=python"
if exist python_cmd.txt set /p PY=<python_cmd.txt
set "RUN=%PY% weekly\common\render_driver.py --scene weekly\2026-09-26_kaleidoscope\kaleidoscope.py --seed 1 --fps 24 --resolution 1920x1080 --speed-test"
echo Testing 1080p at 24 fps, both looks. The first two frames of each test
echo include Blender warming up and are left out of the estimate.
echo.
echo === Standard (EEVEE) ===
%RUN% --engine eevee
echo.
echo === Photoreal (Cycles) ===
%RUN% --engine cycles
echo.
echo Send these numbers over and the settings can be tuned to your computer.
pause
