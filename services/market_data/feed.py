"""Market data feed factory — Coinbase WebSocket or Moomoo daily bars."""

from services.shared.config import IS_EQUITY_MODE, MARKET_DATA_PROVIDER


def start_market_data(logger=None, background=None):
    if MARKET_DATA_PROVIDER == "moomoo" or IS_EQUITY_MODE:
        from services.market_data import moomoo_feed
        from services.shared.config import get_strategy_params

        params = get_strategy_params("InstitutionalTrend")
        # Dashboard: refresh in background so Flask binds immediately.
        bg = True if background is None else background
        moomoo_feed.start(logger=logger, indicator_params=params, background=bg)
        return

    from services.market_data.coinbase_feed import start as start_coinbase

    start_coinbase(logger=logger)
