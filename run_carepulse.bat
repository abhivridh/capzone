@echo off
title CarePulse - Healthcare Monitoring System
echo ============================================================
echo Starting CarePulse Web Application...
echo ============================================================
cd /d "%~dp0"

echo [1/2] Checking database setup...
python setup_database.py

echo.
echo [2/2] Launching CarePulse on http://127.0.0.1:5000 ...
start "" http://127.0.0.1:5000
python app.py

pause
