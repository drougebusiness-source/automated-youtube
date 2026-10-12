#!/usr/bin/env bash
# Run the daily job on your own Mac or Linux computer.
# Schedule it with cron:  crontab -e  then add a line like
#   15 6 * * * /full/path/to/automated-youtube/scripts/run_daily.sh
# (your computer has to be on and awake at that time).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
if [ -d .venv ]; then source .venv/bin/activate; fi
python3 -m ytauto run >> "logs/$(date +%F).log" 2>&1
