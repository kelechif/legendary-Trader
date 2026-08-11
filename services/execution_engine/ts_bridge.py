"""TradeStation bridge: kill switch, log ingest paths, daily halt checks."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from services.shared.config import OPTIONS_CFG, TWMN_ROOT

KILL_SWITCH = TWMN_ROOT / OPTIONS_CFG.get("kill_switch", "data/STOP_TRADING")
TS_PRINT_LOG = TWMN_ROOT / OPTIONS_CFG.get("ts_print_log", "logs/ts_print.csv")
TRADE_LOG = TWMN_ROOT / OPTIONS_CFG.get("trade_log", "data/trades.csv")


def trading_halted() -> bool:
    return KILL_SWITCH.exists()


def halt_trading(reason: str = "manual") -> Path:
    KILL_SWITCH.parent.mkdir(parents=True, exist_ok=True)
    KILL_SWITCH.write_text(f"halted {datetime.now().isoformat()} reason={reason}\n", encoding="utf-8")
    return KILL_SWITCH


def resume_trading() -> bool:
    if KILL_SWITCH.exists():
        KILL_SWITCH.unlink()
        return True
    return False


def ingest_ts_print(since_date: str | None = None) -> list[dict]:
    """Parse TradeStation Print log into trade events."""
    if not TS_PRINT_LOG.exists():
        return []
    rows = []
    with open(TS_PRINT_LOG, newline="", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            # Strategy format: date, time, EVENT, symbol, shift, ...
            # Exporter format: date, time, symbol, GATE_OPEN, shift, close, TOD
            if parts[2] in ("SIM_ENTRY", "SIM_CONVERT", "SESSION_END", "HALT", "GATE_OPEN", "GATE_CLOSED"):
                row = {
                    "date": parts[0],
                    "time": parts[1],
                    "event": parts[2],
                    "symbol": parts[3] if len(parts) > 3 else "",
                    "direction": parts[4] if len(parts) > 4 else "",
                    "source": parts[6] if len(parts) > 6 else "TWMN",
                    "raw": line,
                }
            elif parts[2] in ("GATE_OPEN", "GATE_CLOSED") or (len(parts) > 3 and parts[3] in ("GATE_OPEN", "GATE_CLOSED")):
                row = {
                    "date": parts[0],
                    "time": parts[1],
                    "event": parts[3] if parts[3] in ("GATE_OPEN", "GATE_CLOSED") else parts[2],
                    "symbol": parts[2] if parts[3] in ("GATE_OPEN", "GATE_CLOSED") else "",
                    "direction": parts[4] if len(parts) > 4 else "",
                    "source": "TWMN",
                    "raw": line,
                }
            else:
                row = {
                    "date": parts[0],
                    "time": parts[1],
                    "event": parts[2],
                    "symbol": parts[3] if len(parts) > 3 else "",
                    "direction": "",
                    "source": "",
                    "raw": line,
                }
            if since_date and row["date"] < since_date:
                continue
            rows.append(row)
    return rows


def append_trade_log(row: dict) -> None:
    TRADE_LOG.parent.mkdir(parents=True, exist_ok=True)
    write_header = not TRADE_LOG.exists()
    fieldnames = ["timestamp", "event", "symbol", "direction", "source", "pnl", "notes"]
    with open(TRADE_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerow(row)


def daily_pnl_summary() -> dict:
    if not TRADE_LOG.exists():
        return {"trades": 0, "pnl": 0.0}
    pnl = 0.0
    n = 0
    with open(TRADE_LOG, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("pnl"):
                try:
                    pnl += float(row["pnl"])
                    n += 1
                except ValueError:
                    pass
    max_loss = float(OPTIONS_CFG.get("risk", {}).get("max_daily_loss_pct", 2.0))
    return {"trades": n, "pnl": round(pnl, 2), "halt_recommended": pnl < 0 and abs(pnl) > max_loss * 100}
