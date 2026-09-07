@echo off
REM One-time setup for Portal Machine on Windows.
REM Installs the Python packages and ffmpeg.

REM always work from the folder this script lives in, even when launched
REM "as administrator" (which starts in System32)
cd /d "%~dp0"

REM running straight from inside the ZIP leaves the rest of the files behind
if not exist requirements.txt (
    echo It looks like you are running this from INSIDE the ZIP file.
    echo Right-click PortalMachine.zip, choose "Extract All...", then run
    echo setup.bat from the extracted PortalMachine folder.
    pause
    exit /b 1
)

REM The graphics packages ship prebuilt binaries for Python 3.10 - 3.13.
REM Python 3.14+ is too new for them, so prefer an older install if present.
set "PY="
for %%V in (3.13 3.12 3.11 3.10) do (
    if not defined PY (
        py -%%V -c "exit()" >nul 2>nul && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo No compatible Python found. The video packages need Python 3.10 - 3.13
    echo ^(Python 3.14 is too new for them - it can stay installed, no need to remove it^).
    echo.
    echo Opening the Python downloads page: scroll to a "Python 3.12.x" release,
    echo download the "Windows installer (64-bit)", and CHECK "Add python.exe to PATH"
    echo during install. Then run this setup.bat again.
    start https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

echo Using Python: %PY%
echo %PY%> python_cmd.txt

echo Installing Python packages...
%PY% -m pip install --upgrade pip >nul
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo Package install failed - see the message above.
    pause
    exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo Installing ffmpeg via winget - this can take a minute...
    winget install --id Gyan.FFmpeg.Essentials -e --accept-source-agreements --accept-package-agreements
    echo.
    echo IMPORTANT: close this window and use a NEW window for make_video.bat
    echo so Windows picks up ffmpeg.
)

echo.
echo Setup complete! Double-click make_video.bat to create a video.
pause
