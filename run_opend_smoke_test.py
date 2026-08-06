"""Smoke test: verify OpenD connectivity, fetch klines, scan signals."""

import json
import sys

from services.execution_engine import paper_trader
from services.market_data.asset_registry import register_assets
from services.market_data.feed import start_market_data
from services.market_data.moomoo_feed import load_or_fetch, refresh_asset
from services.market_data.universe import refresh_universe
from services.shared.config import ASSETS, MOOMOO_HOST, MOOMOO_PORT, TRADING_CFG, load_config
from services.shared.logging_setup import setup_logging
from services.strategy_engine import init as init_strategies
from services.strategy_engine.signal_scanner import rank_entry_candidates, scan_universe, summarize_scan


def test_opend_quote():
    from moomoo import AuType, KLType, OpenQuoteContext, RET_OK

    ctx = OpenQuoteContext(MOOMOO_HOST, MOOMOO_PORT)
    try:
        ret, global_state = ctx.get_global_state()
        if ret != RET_OK:
            return False, f"get_global_state failed ret={ret}"
        ret, data, _ = ctx.request_history_kline(
            "US.AAPL",
            start="2024-01-01",
            end="2026-08-05",
            ktype=KLType.K_DAY,
            autype=AuType.QFQ,
        )
        if ret != RET_OK or data is None or data.empty:
            return False, f"request_history_kline failed ret={ret}"
        return True, {"global": global_state, "probe_bars": len(data)}
    finally:
        ctx.close()


def main():
    log = setup_logging()
    cfg = load_config()

    log.info("OpenD smoke test → %s:%s", MOOMOO_HOST, MOOMOO_PORT)

    ok, detail = test_opend_quote()
    if not ok:
        log.error("OpenD not reachable: %s", detail)
        log.error("Start moomoo OpenD and ensure API port %s is open.", MOOMOO_PORT)
        return 1
    log.info("OpenD quote context OK")

    probe = "US.AAPL"
    try:
        df = load_or_fetch(probe, years=2, force_refresh=True)
        log.info("Fetched %s: %d daily bars (%s → %s)", probe, len(df), df.index.min().date(), df.index.max().date())
    except Exception as exc:
        log.error("Kline fetch failed for %s: %s", probe, exc)
        return 1

    tickers = refresh_universe(cfg)
    register_assets(tickers)
    log.info("Universe loaded: %d tickers", len(ASSETS))

    init_strategies()
    sample = ASSETS[: min(10, len(ASSETS))]
    register_assets(sample)
    log.info("Refreshing klines for sample: %s", sample)

    errors = []
    for ticker in sample:
        try:
            candles = refresh_asset(ticker)
            log.info("  %s: %d bars, close=%.2f", ticker, len(candles), candles[-1]["close"] if candles else 0)
        except Exception as exc:
            errors.append((ticker, str(exc)))
            log.error("  %s FAILED: %s", ticker, exc)

    strategy = paper_trader.current_strategy
    params = paper_trader.get_params(strategy)
    scanned = scan_universe(strategy, params, assets=sample)
    summary = summarize_scan(scanned)
    entries = rank_entry_candidates(scanned)[:5]

    log.info("Signal scan: %s", summary)
    log.info("Top entries: %s", entries)

    result = {
        "opend": {"host": MOOMOO_HOST, "port": MOOMOO_PORT, "ok": ok},
        "probe_ticker": probe,
        "probe_bars": len(df),
        "universe_size": len(ASSETS),
        "sample_size": len(sample),
        "refresh_errors": errors,
        "safe_mode": TRADING_CFG.get("safe_mode", True),
        "summary": summary,
        "top_entries": entries,
    }

    print(json.dumps(result, indent=2, default=str))
    return 1 if errors and len(errors) == len(sample) else 0


if __name__ == "__main__":
    sys.exit(main())
