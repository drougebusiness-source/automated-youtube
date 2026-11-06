@echo off
REM Double-click to sign in again (needed once so the bot can post link comments and read watch hours).
cd /d "%~dp0\.."
echo Working in: %CD%
if not exist config.yaml echo WARNING: config.yaml is not in this folder. Move the files so config.yaml, client_secret.json and the scripts folder sit together.
python -m ytauto auth
if not exist token.json (
  echo.
  echo Sign-in did not finish, so there is no token.json yet. Read the message above.
  pause
  exit /b 1
)
echo.
echo Now copy everything in token.json (Notepad opens it) into the GitHub secret YOUTUBE_TOKEN_JSON.
notepad token.json
pause
