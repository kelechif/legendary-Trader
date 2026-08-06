"""Daily pipeline: refresh universe, Moomoo data, run signals."""

import os
import sys

from services.execution_engine import paper_trader
from services.market_data.asset_registry import register_assets
from services.market_data.feed import start_market_data
from services.market_data.universe import refresh_universe
from services.shared.config import ASSETS, IS_EQUITY_MODE, MARKET_DATA_PROVIDER, load_config
from services.shared.logging_setup import setup_logging
from services.strategy_engine import init as init_strategies


def main():
    if MARKET_DATA_PROVIDER != "moomoo" and not IS_EQUITY_MODE:
        print("Daily pipeline requires market_data.provider=moomoo or trading.mode=equity")
        sys.exit(1)

    log = setup_logging()
    log.info("Starting daily equity pipeline")

    cfg = load_config()
    tickers = refresh_universe(cfg)
    register_assets(tickers)
    log.info("Universe: %d tickers", len(ASSETS))

    init_strategies()
    start_market_data(logger=log)
    paper_trader.run_daily_cycle(logger=log)

    log.info("Daily pipeline finished")


if __name__ == "__main__":
    main()
