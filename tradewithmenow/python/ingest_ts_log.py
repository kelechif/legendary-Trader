#!/usr/bin/env python3
"""Ingest TradeStation Print log into normalized trade CSV."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from services.execution_engine.ts_bridge import append_trade_log, ingest_ts_print  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--since", default=None, help="YYYYMMDD minimum date")
    args = p.parse_args()

    events = ingest_ts_print(since_date=args.since)
    for ev in events:
        append_trade_log(
            {
                "timestamp": f"{ev.get('date', '')} {ev.get('time', '')}",
                "event": ev.get("event", ""),
                "symbol": ev.get("symbol", ""),
                "direction": ev.get("direction", ""),
                "source": ev.get("source", "TWMN"),
                "pnl": "",
                "notes": ev.get("raw", ""),
            }
        )
    print(f"Ingested {len(events)} events at {datetime.now().isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
