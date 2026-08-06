#!/usr/bin/env python3
"""Daily 0DTE summary: ingest TS log, check halt, print report."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from services.execution_engine.ts_bridge import (  # noqa: E402
    daily_pnl_summary,
    ingest_ts_print,
    trading_halted,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--since", default=None)
    args = p.parse_args()

    events = ingest_ts_print(since_date=args.since)
    summary = daily_pnl_summary()
    halted = trading_halted()

    print(f"=== 0DTE Daily Report {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    print(f"Kill switch active: {halted}")
    print(f"TS events ingested: {len(events)}")
    print(f"Trade log: {summary}")
    if summary.get("halt_recommended"):
        print("WARNING: daily loss threshold may be breached — consider halt_trading()")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
