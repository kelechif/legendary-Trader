@echo off
setlocal
set ROOT=%~dp0..
set QP=%ROOT%\..\Quant-Platform
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
if not exist "%ROOT%\data" mkdir "%ROOT%\data"
echo === CTV SIM logging ===
echo TS print log: %ROOT%\logs\ts_print.csv
echo.
if exist "%QP%\run_0dte_report.py" (
  pushd "%QP%"
  python tradewithmenow\python\ingest_ts_log.py
  python run_0dte_report.py
  popd
) else (
  python "%ROOT%\python\ingest_ts_log.py"
)
echo.
echo Done. Keep TradeStation SIM running with CTV_ConvertVert_Strategy applied.
pause
