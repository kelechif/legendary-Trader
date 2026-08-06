# Michael's CTV Workspace — SIM Auto-Logging Setup

Wire **T2_TWMN_CTV_V3.0** indicators to our automation layer on workspace  
`TradeStation/Workspaces/CTV_May26_Michaels.tsw`.

## One-time: Import EasyLanguage scaffolds

1. Open **TradeStation** → **Development Environment** (TDE)
2. **File → Import** → select all from `easylanguage/`:
   - `CTV_TWMN_Bridge.els`
   - `CTV_0DTE_RegimeGate.els`
   - `CTV_ConvertVert_Strategy.els`
   - `CTV_SignalExporter.els`
3. Verify **Verify** compiles each (fix Data stream numbers if needed)

## Open Michael's workspace

1. **File → Open Workspace** →  
   `TradeWithMeNow\TradeStation\Workspaces\CTV_May26_Michaels.tsw`
2. Confirm these TWMN studies are present (from CTV ELD):
   - `T2_TWMN_Shift`
   - `T2_TWMN_Mark_TOD_Auto`
   - `T2_TWMN_Bar_Dir`
   - `T2_TWMN_Current_Energy`
   - `T2_TWMN_Expected_Move`
   - `T2_TWMN_MA_Trend`

## Chart setup (SPX 5-minute SIM)

1. Set account to **Simulated**
2. Primary symbol: **@SPX** (or **@XSP** for smaller account), **5 min**
3. Add **$VIX.X** as **Data2** (VIX filter)
4. Note **Data Series** order (Format Symbol → Data Series tab):

| Data # | Symbol / Study | Used by |
|--------|----------------|---------|
| 1 | @SPX 5m | Price + strategy |
| 2 | $VIX.X | Regime gate VIX max |
| 3+ | TWMN studies on hidden/subgraph streams | Bridge inputs |

5. Apply studies **in this order** on the SPX chart:
   - Existing TWMN stack (from workspace)
   - **CTV_TWMN_Bridge** — set `ShiftDataNum`, `TODDataNum`, `BarDirDataNum`, `EnergyDataNum` to match your Data series numbers for each TWMN study
   - **CTV_0DTE_RegimeGate** — `UseTWMNBridge=true`, `VixDataNum=2`
   - **CTV_SignalExporter** — logs gate changes
6. Apply **Strategy**: **CTV_ConvertVert_Strategy**
   - `SafeMode = true` (SIM logging only, no orders)
   - `UseTWMNBridge = true`
   - `UseRegimeGate = true`

## Calibrate Data stream numbers

After applying TWMN indicators, open **Format Symbol → Data Series** and note each study's Data #.

Typical Michael's layout (adjust to your chart):

```
ShiftDataNum    = Data # for T2_TWMN_Shift Plot1 (ShiftTotal)
TODDataNum      = Data # for T2_TWMN_Mark_TOD_Auto
BarDirDataNum   = Data # for T2_TWMN_Bar_Dir
EnergyDataNum   = Data # for T2_TWMN_Current_Energy
```

Use **EasyLanguage Output Bar** or **Print Log** to confirm `TWMN_ShiftRaw` moves on Holy Shift.

## Automated SIM logging

Run from `TradeWithMeNow` folder:

```bat
setup\run_sim_logging.bat
setup\watch_sim_logging.bat
```

`watch_sim_logging.bat` polls `logs\ts_print.csv` every 60s during the session.

Or manually:

```bat
mkdir logs 2>nul
python python\ingest_ts_log.py
python ..\Quant-Platform\run_0dte_report.py
```

TradeStation writes to `logs\ts_print.csv`. Python ingests into `data\trades.csv`.

## Enable live SIM orders (Phase 2)

When logging looks correct for 1–2 weeks:

1. Set `SafeMode = false` on **CTV_ConvertVert_Strategy**
2. Confirm **Options Level 4+** and SPX 0DTE permissions
3. Start with **1 ticket/day**, `MaxRiskPct = 0.5`

## Kill switch

Create file `data\STOP_TRADING` to halt Python-side reporting alerts;  
set `StopTrading` manually in strategy inputs or disable strategy.

## TWMN GlobalSignal map

| Slot | Source | Meaning |
|------|--------|---------|
| 1 | CTV_TWMN_Bridge | ShiftDir (-1/0/+1) |
| 2 | CTV_TWMN_Bridge | TODActive |
| 3 | CTV_TWMN_Bridge | BarDir raw |
| 4 | CTV_TWMN_Bridge | EnergyOK |
| 5 | CTV_TWMN_Bridge | TWMN composite gate |
| 10 | CTV_0DTE_RegimeGate | Full regime gate |
| 11 | CTV_0DTE_RegimeGate | ShiftDir (pass-through) |
