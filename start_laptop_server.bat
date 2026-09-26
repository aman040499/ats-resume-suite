@echo off
title ATS Resume Studio - Laptop Cloud Server
echo ========================================================
echo   Launching ATS Resume Studio on Local Server...
echo ========================================================

:: Check Python venv
if exist "%~dp0.venv\Scripts\activate.bat" (
    call "%~dp0.venv\Scripts\activate.bat"
)

:: Check if cloudflared is installed or available in folder
where cloudflared >nul 2>nul
if %errorlevel% neq 0 (
    if not exist "%~dp0cloudflared.exe" (
        echo [INFO] Downloading Cloudflare Tunnel (cloudflared.exe) for free public HTTPS link...
        powershell -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%~dp0cloudflared.exe'"
    )
    set "CF_CMD=%~dp0cloudflared.exe"
) else (
    set "CF_CMD=cloudflared"
)

echo [1/2] Starting Streamlit Web App on localhost:8501...
start "Streamlit WebApp" /min cmd /c "streamlit run app.py --server.port 8501 --server.headless true"

echo [2/2] Generating Free Global HTTPS Web Link via Cloudflare Tunnel...
echo.
echo ========================================================
echo   YOUR SECURE PUBLIC WEB LINK WILL APPEAR BELOW:
echo   (Share this link to access from any phone or computer)
echo ========================================================
echo.

"%CF_CMD%" tunnel --url http://localhost:8501
pause
