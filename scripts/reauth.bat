@echo off
REM Double-click to sign in to YouTube again. The sign-in goes straight into the GitHub secret
REM YOUTUBE_TOKEN_JSON (through the GitHub CLI); it is never saved to a file here.
cd /d "%~dp0\.."
for %%f in (client_secret*.json) do set CLIENT=%%f
if not defined CLIENT (
  echo No client_secret*.json in %CD%. Download it from Google Cloud ^(APIs ^& Services ^> Credentials^).
  pause
  exit /b 1
)
python -m ytauto signin "%CLIENT%"
pause
