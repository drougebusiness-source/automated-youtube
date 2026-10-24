@echo off
REM Double-click to upload batch videos that are still waiting (after YouTube's daily limit).
cd /d "%~dp0\.."
python -m ytauto upload-pending
pause
