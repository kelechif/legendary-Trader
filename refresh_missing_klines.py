"""Retry kline fetch for tickers missing from local cache."""

import sys

from services.market_data.asset_registry import register_assets
from services.market_data.moomoo_feed import _kline_path, refresh_asset
from services.market_data.universe import refresh_universe
from services.shared.config import ASSETS, load_config
from services.shared.logging_setup import setup_logging


def missing_tickers() -> list[str]:
    missing = []
    for ticker in ASSETS:
        if not _kline_path(ticker).exists():
            missing.append(ticker)
    return missing


def main():
    log = setup_logging()
    cfg = load_config()
    refresh_universe(cfg)
    register_assets(ASSETS)

    missing = missing_tickers()
    if not missing:
        log.info("All %d universe tickers have cached klines", len(ASSETS))
        print(f"OK: {len(ASSETS)}/{len(ASSETS)} cached")
        return 0

    log.info("Retrying %d missing tickers: %s", len(missing), missing[:10])
    errors = []
    for ticker in missing:
        try:
            candles = refresh_asset(ticker)
            log.info("  %s: %d bars", ticker, len(candles))
        except Exception as exc:
            errors.append((ticker, str(exc)))
            log.error("  %s FAILED: %s", ticker, exc)

    still_missing = missing_tickers()
    print(f"Cached: {len(ASSETS) - len(still_missing)}/{len(ASSETS)}")
    if still_missing:
        print("Still missing:", still_missing)
    if errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
