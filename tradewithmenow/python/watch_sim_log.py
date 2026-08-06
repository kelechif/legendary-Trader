#!/usr/bin/env python3
"""Poll TradeStation ts_print.csv and ingest new lines during SIM sessions."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from services.execution_engine.ts_bridge import (  # noqa: E402
    TS_PRINT_LOG,
    append_trade_log,
    daily_pnl_summary,
    ingest_ts_print,
    trading_halted,
)


def _line_key(line: str) -> str:
    return line.strip()


def watch(interval_sec: float = 60.0, since_date: str | None = None) -> None:
    seen: set[str] = set()
    if TS_PRINT_LOG.exists():
        for row in ingest_ts_print(since_date=since_date):
            seen.add(row["raw"])

    print(f"Watching {TS_PRINT_LOG} every {interval_sec:.0f}s (Ctrl+C to stop)")
    while True:
        if trading_halted():
            print(f"[{datetime.now():%H:%M:%S}] Kill switch active — skipping ingest")

        new_count = 0
        for row in ingest_ts_print(since_date=since_date):
            key = row["raw"]
            if key in seen:
                continue
            seen.add(key)
            append_trade_log(
                {
                    "timestamp": f"{row.get('date', '')} {row.get('time', '')}",
                    "event": row.get("event", ""),
                    "symbol": row.get("symbol", ""),
                    "direction": row.get("direction", ""),
                    "source": row.get("source", "TWMN"),
                    "pnl": "",
                    "notes": key,
                }
            )
            new_count += 1
            print(f"[{datetime.now():%H:%M:%S}] + {row.get('event')} {row.get('symbol')} dir={row.get('direction')}")

        if new_count:
            summary = daily_pnl_summary()
            print(f"  journal: {summary}")

        time.sleep(interval_sec)


def main() -> int:
    p = argparse.ArgumentParser(description="Watch ts_print.csv and ingest new SIM events")
    p.add_argument("--interval", type=float, default=60.0, help="Poll interval seconds")
    p.add_argument("--since", default=None, help="YYYYMMDD minimum date")
    args = p.parse_args()

    try:
        watch(interval_sec=args.interval, since_date=args.since)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
