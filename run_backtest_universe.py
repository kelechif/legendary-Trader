"""Run multi-asset universe backtest from cached klines."""

import argparse
import json
import sys

from services.market_data.moomoo_feed import load_cached_candles
from services.shared.config import ASSETS, TRADING_CFG, get_strategy_params, load_config
from services.shared.logging_setup import setup_logging
from services.training_engine.universe_backtest import run_backtest_universe


def main():
    parser = argparse.ArgumentParser(description="Backtest strategy across full universe")
    parser.add_argument("--strategy", default="InstitutionalTrend")
    parser.add_argument("--limit", type=int, default=0, help="Max tickers (0 = all)")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args()

    log = setup_logging()
    cfg = load_config()
    params = get_strategy_params(args.strategy)
    tickers = ASSETS[: args.limit] if args.limit else ASSETS

    ticker_candles = {}
    skipped = []
    for ticker in tickers:
        candles = load_cached_candles(ticker, params)
        if len(candles) >= 220:
            ticker_candles[ticker] = candles
        else:
            skipped.append(ticker)

    if not ticker_candles:
        log.error("No cached klines found. Run: python run_daily.py")
        return 1

    log.info("Backtesting %d tickers (%d skipped)", len(ticker_candles), len(skipped))
    result = run_backtest_universe(
        ticker_candles,
        args.strategy,
        params=params,
        initial_equity=float(cfg.get("initial_equity", 100000)),
        max_positions=int(TRADING_CFG.get("max_positions", 10)),
        slippage_bps=float(TRADING_CFG.get("slippage_bps", 5)),
        commission=float(TRADING_CFG.get("commission", 1.0)),
        regime_cfg=TRADING_CFG.get("regime", {}),
    )

    if "error" in result:
        log.error(result["error"])
        return 1

    m = result["metrics"]
    log.info(
        "Universe backtest: CAGR proxy equity=%.0f Sharpe=%.2f MaxDD=%.1f%% Trades=%d",
        m["current_equity"],
        m["sharpe"],
        m["max_drawdown_pct"],
        m["total_trades"],
    )
    log.info("Top contributors: %s", result.get("top_contributors", [])[:5])

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        log.info("Wrote %s", args.output)
    else:
        print(json.dumps({"metrics": m, "top_contributors": result.get("top_contributors", [])[:10]}, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
