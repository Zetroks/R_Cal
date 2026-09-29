@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found.
    pause
    exit /b 1
)

echo Starting Telegram bot ...

.venv\Scripts\python.exe -m CalendarBot.bot

pause
