@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Create it first:
    echo     C:\Python313\python.exe -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting Desktop client (server: %CAL_SERVER_URL%) ...

.venv\Scripts\python.exe -m CalendarDesktop.main

pause
