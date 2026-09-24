@echo off
REM Measures how fast YOUR computer renders Blender Worlds, and estimates how
REM long 10-minute, 1-hour and 3-hour videos would take. Takes a few minutes.

cd /d "%~dp0"
set "PY=python"
if exist python_cmd.txt set /p PY=<python_cmd.txt

echo Testing 1080p at standard quality. The first two frames are slow
echo while Blender warms up; they are left out of the estimate.
echo.
%PY% blender_worlds\make_world.py --speed-test --resolution 1920x1080 --quality standard --seed 12345
echo.
echo Tip: "draft" quality renders faster; 1440p and 4K take roughly 1.8x and 4x longer.
pause
