"""Quant Platform entry point."""

import os

from services.dashboard.app import create_app
from services.execution_engine import paper_trader
from services.market_data.asset_registry import register_assets
from services.market_data.feed import start_market_data
from services.shared.config import ASSETS, DEFAULT_PORT, IS_EQUITY_MODE, MARKET_DATA_PROVIDER
from services.shared.logging_setup import setup_logging
from services.strategy_engine import init as init_strategies


def main():
    log = setup_logging()
    register_assets(ASSETS)
    log.info(
        "Starting Quant Platform (provider=%s, equity=%s, assets=%d)",
        MARKET_DATA_PROVIDER,
        IS_EQUITY_MODE,
        len(ASSETS),
    )

    init_strategies()
    from services.strategy_engine.registry import list_strategies
    log.info("Loaded strategies: %s", list_strategies())

    start_market_data(logger=log)
    if not IS_EQUITY_MODE:
        from services.market_data.order_book_rest import start as start_order_book
        start_order_book()
    paper_trader.start()

    port = int(os.environ.get("PORT", DEFAULT_PORT))
    if IS_EQUITY_MODE or MARKET_DATA_PROVIDER == "moomoo":
        log.info(
            "Dashboard listening on http://0.0.0.0:%s (Moomoo klines loading in background)",
            port,
        )
    else:
        log.info("Market data and execution engine started")

    create_app().run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
