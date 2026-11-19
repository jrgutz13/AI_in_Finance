@echo off
REM Enhance Clips: string a folder of clips into one long video from a plan
REM you write (order, slow motion, trims, music). Drag the clips folder onto
REM this file, or double-click and drag it in when asked.
REM First run: writes clips_plan.txt into the folder and opens it in Notepad.
REM Prompts use labels + goto, not if-blocks.

cd /d "%~dp0"

set "PY=python"
if exist python_cmd.txt set /p PY=<python_cmd.txt

set "FOLDER=%~1"
if not "%FOLDER%"=="" goto :have_folder
set /p FOLDER="Drag your folder of clips here, then press Enter: "
:have_folder
set "FOLDER=%FOLDER:"=%"

%PY% enhance_clips.py "%FOLDER%" --confirm
if errorlevel 3 goto :new_plan
if errorlevel 1 goto :failed
echo.
echo Done! The video is in the output folder.
start "" "%~dp0output"
pause
exit /b 0

:new_plan
echo.
echo Opening the plan in Notepad. Edit it, save it, then run enhance_clips.bat again.
start "" notepad "%FOLDER%\clips_plan.txt"
pause
exit /b 0

:failed
echo.
echo Stopped - see the message above.
pause
exit /b 1
