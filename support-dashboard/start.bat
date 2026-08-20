@echo off
REM Double-click launcher for Windows.
REM Starts the dashboard server and opens it in your browser.

cd /d "%~dp0"

REM Find a Python 3 launcher: prefer the py launcher, fall back to python.
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo Python 3.11+ is required but was not found.
  echo Install it from https://www.python.org/downloads/ ^(tick "Add to PATH"^) and try again.
  pause
  exit /b 1
)

echo Starting the Support Performance Dashboard...
echo It will open at http://localhost:8791
echo Leave this window open while you use it. Press Ctrl+C here to stop.
echo.

REM Open the browser after a short delay, then run the server in this window.
start "" /b cmd /c "timeout /t 2 >nul & start "" http://localhost:8791"
%PY% serve.py

pause
