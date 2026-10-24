@echo off
REM Double-click to make a batch of videos on this PC and upload them as private.
REM Free: uses your computer instead of GitHub's servers. Keep the PC awake while it runs.
cd /d "%~dp0\.."
set /p DAYS="How many days of videos? (e.g. 14): "
set /p START="First date YYYY-MM-DD (leave empty for tomorrow): "
if "%START%"=="" (python -m ytauto batch --days %DAYS%) else (python -m ytauto batch --days %DAYS% --start %START%)
echo.
echo Done. If some uploads are still waiting, run upload_pending.bat tomorrow.
pause
