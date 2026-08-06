#!/usr/bin/env python3
"""Run 0DTE backtest on session bar CSV."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from services.options_engine.backtest import run_regime_backtest  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--bars", required=True, help="CSV: date,time,close")
    p.add_argument("--width", type=float, default=10.0)
    p.add_argument("--credit", type=float, default=1.20)
    p.add_argument("--direction", default="bullish")
    p.add_argument("--output", default="")
    args = p.parse_args()

    result = run_regime_backtest(
        Path(args.bars),
        width=args.width,
        credit=args.credit,
        direction=args.direction,
    )
    text = json.dumps(result, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
