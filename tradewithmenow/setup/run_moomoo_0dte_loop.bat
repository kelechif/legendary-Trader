@echo off
setlocal
pushd %~dp0\..
echo === 0DTE Moomoo auto-loop (Ctrl+C to stop) ===
python run_0dte_moomoo_loop.py %*
popd
