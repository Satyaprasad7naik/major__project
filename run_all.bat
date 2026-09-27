@echo off
title DerivInsight Unified System Launcher
cls
echo ============================================================
echo   DerivInsight Unified System (Project 1 + Project 2)
echo ============================================================
echo.
echo [1/2] Starting Project 1 (FastAPI Backend on Port 8080)...
start "Project 1 - FastAPI Backend (Port 8080)" cmd /k "cd /d "%~dp0" && python -m uvicorn app.main:app --host 127.0.0.1 --port 8080"

echo [2/2] Starting Project 2 (Next.js App Router on Port 3000)...
start "Project 2 - Next.js App Router (Port 3000)" cmd /k "cd /d "%~dp0frontend-next" && npx next dev --port 3000"

echo.
echo Waiting 3 seconds for servers to initialize...
ping -n 4 127.0.0.1 >nul

echo Opening DerivInsight in default browser...
start http://localhost:8080

echo.
echo ============================================================
echo   SUCCESS! Both projects are running in separate windows.
echo.
echo   - Project 1 (Main Website + Embedded Project 2): http://localhost:8080
echo   - Project 2 (Standalone Next.js App Router):     http://localhost:3000
echo   - FastAPI OpenAPI Documentation:                http://localhost:8080/docs
echo ============================================================
echo.
pause
