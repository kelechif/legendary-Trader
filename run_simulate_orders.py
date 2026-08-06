"""Run daily pipeline with Moomoo SIMULATE orders enabled."""

import json
import sys

from services.execution_engine import paper_trader
from services.execution_engine.moomoo_broker import get_account_snapshot, use_moomoo_broker
from services.market_data.asset_registry import register_assets
from services.market_data.feed import start_market_data
from services.market_data.universe import refresh_universe
from services.shared.config import ASSETS, IS_EQUITY_MODE, MARKET_DATA_PROVIDER, TRADING_CFG, load_config
from services.shared.logging_setup import setup_logging
from services.strategy_engine import init as init_strategies
from services.strategy_engine.signal_scanner import rank_entry_candidates, scan_universe, summarize_scan


def main():
    log = setup_logging()
    cfg = load_config()

    if not use_moomoo_broker():
        log.error("Set trading.broker: moomoo in config/local.yaml")
        return 1
    if TRADING_CFG.get("safe_mode", True):
        log.error("Set trading.safe_mode: false to route orders to OpenD SIMULATE")
        return 1
    if MARKET_DATA_PROVIDER != "moomoo" and not IS_EQUITY_MODE:
        log.error("Equity/Moomoo mode required")
        return 1

    snap = get_account_snapshot()
    log.info("SIMULATE account: %s", snap)
    if snap.get("power", 0) <= 0:
        log.warning(
            "Buying power is 0 — new BUY orders will be skipped. "
            "Reset paper account in moomoo app (Me → Paper Trading → Reset Card). "
            "SELL exits on existing positions will still execute."
        )

    tickers = refresh_universe(cfg)
    register_assets(tickers)
    log.info("Universe: %d tickers", len(ASSETS))

    init_strategies()
    start_market_data(logger=log)
    paper_trader.run_daily_cycle(logger=log)

    strategy = paper_trader.current_strategy
    params = paper_trader.get_params(strategy)
    scanned = scan_universe(strategy, params)
    summary = summarize_scan(scanned)
    entries = rank_entry_candidates(scanned)[:10]

    result = {
        "broker": "moomoo",
        "env": TRADING_CFG.get("env", "SIMULATE"),
        "account": snap,
        "summary": summary,
        "top_entries": entries,
    }
    print(json.dumps(result, indent=2, default=str))
    log.info("Simulate order run complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
