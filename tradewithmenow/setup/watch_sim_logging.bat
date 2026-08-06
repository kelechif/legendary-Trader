@echo off
setlocal
set ROOT=%~dp0..
set QP=%ROOT%\..\Quant-Platform
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
if not exist "%ROOT%\data" mkdir "%ROOT%\data"
echo === CTV SIM watch (60s poll) ===
echo Log: %ROOT%\logs\ts_print.csv
echo Press Ctrl+C to stop.
echo.
pushd "%QP%"
python tradewithmenow\python\watch_sim_log.py --interval 60
popd
