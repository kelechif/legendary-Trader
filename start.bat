@echo off
set PORT=8050
echo Stopping any process on port %PORT%...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :%PORT% ^| findstr LISTENING') do taskkill /PID %%a /F 2>nul
timeout /t 2 /nobreak >nul
echo Starting Quant Platform dashboard on http://127.0.0.1:%PORT% ...
echo Mission UI (prop_algo) stays on http://127.0.0.1:8080 when compose is up.
py -3 run.py
