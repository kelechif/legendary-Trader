#!/usr/bin/env python3
"""Auto-loop: ZeroDTERegime on live SPY 5m → Moomoo 0DTE verticals."""

from __future__ import annotations

import argparse
import json
import sys

from services.execution_engine.moomoo_options_broker import use_moomoo_options
from services.options_engine.zero_dte_loop import run_loop, run_once
from services.shared.config import load_config
from services.shared.logging_setup import setup_logging
from services.strategy_engine.registry import init as init_strategies


def main() -> int:
    p = argparse.ArgumentParser(description="0DTE Moomoo auto-loop")
    p.add_argument("--once", action="store_true", help="Single tick then exit")
    p.add_argument("--interval", type=float, default=None, help="Poll seconds (default from config)")
    p.add_argument("--max", type=int, default=None, help="Max loop iterations")
    p.add_argument("--dry-run", action="store_true", help="Force safe_mode")
    args = p.parse_args()

    log = setup_logging()
    cfg = load_config()
    init_strategies()

    if not use_moomoo_options():
        log.error("Set options.execution.broker: moomoo in config/local.yaml")
        return 1

    if args.dry_run:
        from services.shared import config as shared_config

        shared_config.OPTIONS_CFG.setdefault("moomoo", {})["safe_mode"] = True

    if args.once:
        result = run_once()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("status") != "error" else 1

    log.info("Starting 0DTE loop (Ctrl+C to stop)")
    try:
        run_loop(interval_sec=args.interval, max_iterations=args.max)
    except KeyboardInterrupt:
        log.info("Loop stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
