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

echo Starting Uvicorn on %CAL_SERVER_HOST%:%CAL_SERVER_PORT% ...

.venv\Scripts\python.exe -m CalendarServer.main

pause
