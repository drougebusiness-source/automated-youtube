@echo off
REM Run the daily job on your own Windows computer.
REM Schedule it in Task Scheduler: Create Basic Task > Daily > Start a program > this file.
cd /d "%~dp0\.."
if not exist logs mkdir logs
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python -m ytauto run >> logs\daily.log 2>&1
