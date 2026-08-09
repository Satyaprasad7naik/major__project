@echo off
title DerivInsight - AI SQL Assistant & Sentinel Control
color 0A
cls

echo ================================================================
echo          DERIVINSIGHT - CYBER INTELLIGENCE PLATFORM            
echo ================================================================
echo.

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo [1/3] Checking Python environment...
if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
    echo     [+] Virtual environment detected: venv
    set PYTHON_CMD="%SCRIPT_DIR%venv\Scripts\python.exe"
) else (
    echo     [!] Virtual environment not found, using system Python
    set PYTHON_CMD=python
)

echo.
echo [2/3] Scheduling browser auto-open (waiting 5 seconds for server boot)...
start "" cmd /c "timeout /t 5 /nobreak >nul && start http://localhost:8080"

echo.
echo [3/3] Starting FastAPI Application Server on http://127.0.0.1:8080 ...
echo     Press Ctrl+C to stop the server.
echo ================================================================
echo.

%PYTHON_CMD% -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload

echo.
echo Server stopped.
pause
