@echo off
REM Double-click to give every uploaded batch video its publish date and time.
cd /d "%~dp0\.."
python -m ytauto schedule
pause
