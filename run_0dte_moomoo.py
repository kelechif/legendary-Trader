#!/usr/bin/env python3
"""Run 0DTE credit vertical on Moomoo OpenD (SIMULATE default)."""

from __future__ import annotations

import argparse
import json
import sys

from services.execution_engine.moomoo_options_broker import use_moomoo_options
from services.options_engine.zero_dte_executor import execute_0dte_signal, session_status
from services.shared.config import OPTIONS_CFG, load_config
from services.shared.logging_setup import setup_logging


def main() -> int:
    p = argparse.ArgumentParser(description="Moomoo 0DTE vertical executor")
    p.add_argument("--direction", choices=["bullish", "bearish"], default=None)
    p.add_argument("--status", action="store_true", help="Print session status only")
    p.add_argument("--dry-run", action="store_true", help="Force safe_mode for this run")
    args = p.parse_args()

    log = setup_logging()
    load_config()

    if not use_moomoo_options():
        log.error("Set options.execution.broker: moomoo and options.moomoo in config/local.yaml")
        return 1

    if args.dry_run:
        OPTIONS_CFG.setdefault("moomoo", {})["safe_mode"] = True

    if args.status:
        print(json.dumps(session_status(), indent=2, default=str))
        return 0

    direction = args.direction
    if not direction:
        log.error("Pass --direction bullish|bearish or use --status")
        return 1

    result = execute_0dte_signal(direction)
    print(json.dumps(result, indent=2, default=str))
    log.info("0DTE Moomoo run: %s", result.get("status"))
    return 0 if result.get("status") in ("ok", "simulated", "skipped") else 1


if __name__ == "__main__":
    sys.exit(main())
