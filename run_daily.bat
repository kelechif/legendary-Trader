@ECHO OFF
cd /d %~dp0
if not exist config\local.yaml (
  copy config\equity.yaml.example config\local.yaml
)
echo Refreshing universe...
python refresh_universe.py --source file
python run_daily.py
pause
