# TradeWithMeNow 0DTE Bot — TWMN CTV wired

See **SETUP_Michaels_SIM.md** for full Michael's workspace setup.

## TWMN indicators (from CTV_May26_Michaels.tsw)

| Study | Role |
|-------|------|
| `T2_TWMN_Shift` | Holy Shift → GlobalSignal(1) |
| `T2_TWMN_Mark_TOD_Auto` | Time-of-day window → GlobalSignal(2) |
| `T2_TWMN_Bar_Dir` | Bar direction confirm |
| `T2_TWMN_Current_Energy` | Energy gate |

## EasyLanguage import order

1. `CTV_TWMN_Bridge.els` — reads TWMN plots, publishes GlobalSignals 1–5
2. `CTV_0DTE_RegimeGate.els` — time + VIX + regime → GlobalSignals 10–11
3. `CTV_SignalExporter.els` — logs gate changes
4. `CTV_ConvertVert_Strategy.els` — SIM logging / orders

## SIM logging (one command)

```bat
setup\run_sim_logging.bat
```

**During session** (auto-ingest every 60s while TradeStation runs):

```bat
setup\watch_sim_logging.bat
```

## Config reference

`config/twmn_signals.yaml` — indicator names + default Data stream numbers

## Quant-Platform (research + oversight)

```bash
# Merge options config
copy config\options.yaml.example config\local.yaml

# Ingest TradeStation prints
python tradewithmenow\python\ingest_ts_log.py

# Daily report + halt check
python run_0dte_report.py

# Backtest (needs bar CSV with date,time,close)
python tradewithmenow\python\backtest_0dte.py --bars data\spx_5m.csv
```

## Kill switch

Create `data/STOP_TRADING` to halt new entries (read by Python bridge; wire into EL strategy manually or via file check).

## Config

| File | Purpose |
|------|---------|
| `config/0dte_risk.yaml` | Risk limits, structure defaults |
| `config/windows.yaml` | Time-of-day windows |

Quant-Platform reads paths via `config/local.yaml` → `options.twmn_root`.

## Phases

1. **Signal-only** — Regime gate study, log shifts manually
2. **SIM SafeMode** — Strategy prints SIM_ENTRY/SIM_CONVERT to CSV
3. **Ingest + optimize** — Python journal, backtest width/credit
4. **Live small** — SafeMode=false, 0.75% risk per ticket
