#!/usr/bin/env python3
"""0DTE backtest — simple or realistic (OpenD chain credits + max-loss)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from services.options_engine.backtest import run_regime_backtest
from services.options_engine.backtest_realistic import run_realistic_backtest
from services.options_engine.moomoo_intraday import fetch_intraday_candles
from services.shared.config import OPTIONS_CFG, load_config
from services.strategy_engine.registry import init as init_strategies


def main() -> int:
    p = argparse.ArgumentParser(description="0DTE regime backtest")
    p.add_argument("--days-back", type=int, default=30)
    p.add_argument("--width", type=float, default=5.0)
    p.add_argument("--credit", type=float, default=0.50, help="Fixed credit (simple mode only)")
    p.add_argument("--short-delta", type=float, default=0.12)
    p.add_argument("--stop-multiple", type=float, default=None, help="Stop at N× credit loss (default from config)")
    p.add_argument("--realistic", action="store_true", help="Chain credits + dual windows + max-loss")
    p.add_argument("--bars-csv", default="")
    p.add_argument("--output", default="")
    args = p.parse_args()

    load_config()
    init_strategies()

    if args.bars_csv:
        import csv

        candles = []
        with open(args.bars_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                candles.append(
                    {
                        "open": float(row["close"]),
                        "high": float(row["close"]),
                        "low": float(row["close"]),
                        "close": float(row["close"]),
                        "time_hhmm": int(str(row.get("time", "1000")).replace(":", "")[:4]),
                        "time_key": f"{row.get('date', '')} {row.get('time', '')}",
                    }
                )
    else:
        owner = OPTIONS_CFG.get("moomoo", {}).get("underlying", "US.SPY")
        candles = fetch_intraday_candles(owner, days_back=args.days_back, max_bars=8000)
        if not candles:
            print(json.dumps({"error": "No bars from OpenD — is OpenD running?"}))
            return 1

    if args.realistic:
        result = run_realistic_backtest(
            candles,
            width=args.width,
            short_delta=args.short_delta,
            stop_loss_credit_multiple=args.stop_multiple,
        )
        default_out = "data/0dte_backtest_realistic.json"
    else:
        result = run_regime_backtest(candles, width=args.width, credit=args.credit)
        default_out = "data/0dte_backtest_result.json"

    text = json.dumps(result, indent=2, default=str)
    print(text)
    out = Path(args.output or default_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
