@echo off
TITLE InsightOS - Tally Auto Sync Daemon
COLOR 0A
echo ==============================================================================
echo              InsightOS: Automated Tally to Live Data Sync Service
echo ==============================================================================
echo.
echo Checking Python environment...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ and try again.
    pause
    exit /b 1
)

echo Starting Automated Tally Sync Daemon (polling Tally at http://localhost:9000)...
echo Excel spreadsheets will be auto-saved to live_data/ and ingested into InsightOS.
echo Press CTRL+C to stop.
echo.

python scripts\tally_auto_exporter.py --host localhost --port 9000 --interval 300 --live-data-dir live_data

pause
