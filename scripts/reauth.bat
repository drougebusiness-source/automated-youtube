@echo off
REM Double-click to sign in again (needed once so the bot can post link comments).
cd /d "%~dp0\.."
python -m ytauto auth
echo.
echo Now copy everything in token.json (Notepad opens it) into the GitHub secret YOUTUBE_TOKEN_JSON.
notepad token.json
pause
