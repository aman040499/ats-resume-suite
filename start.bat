@echo off
title AI Job Hunter Dashboard (Port 8501)
cd /d "%~dp0"
echo ==========================================================
echo    AI Job Hunter & ATS Gatekeeper (>= 70%% Match)
echo    Dashboard: http://localhost:8501
echo    (Keep this window open while using the dashboard)
echo ==========================================================
".venv\Scripts\python.exe" -m streamlit run app.py
pause
