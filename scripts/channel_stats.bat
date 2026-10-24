@echo off
REM Double-click for a views/likes report, grouped by thumbnail design, theme and length.
cd /d "%~dp0\.."
python -m ytauto stats
echo.
echo Full table saved to output\stats.csv (opens in Excel).
pause
