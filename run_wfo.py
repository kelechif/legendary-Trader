"""Walk-forward optimization CLI for InstitutionalTrend universe backtest."""

import argparse
import json
import sys

from services.market_data.moomoo_feed import load_raw_kline_cache
from services.shared.config import ASSETS, TRADING_CFG, get_strategy_params, load_config
from services.shared.logging_setup import setup_logging
from services.training_engine.wfo import run_walk_forward
from services.training_engine.wfo_grids import GRIDS, combo_count


def main():
    parser = argparse.ArgumentParser(description="Walk-forward optimize strategy params")
    parser.add_argument("--strategy", default="InstitutionalTrend")
    parser.add_argument("--grid", default="expanded", choices=list(GRIDS.keys()))
    parser.add_argument("--limit", type=int, default=0, help="Max tickers (0 = all)")
    parser.add_argument("--folds", type=int, default=0, help="Max folds (0 = auto)")
    parser.add_argument("--max-combos", type=int, default=0, help="Random sample cap (0 = all)")
    parser.add_argument("--train-bars", type=int, default=756, help="IS window (~3y daily)")
    parser.add_argument("--test-bars", type=int, default=126, help="OOS window (~6m daily)")
    parser.add_argument("--step-bars", type=int, default=126, help="Fold step (~6m daily)")
    parser.add_argument("--objective", default="sharpe", choices=["sharpe", "win_rate_pct"])
    parser.add_argument("--output", default="data/wfo_results.json")
    parser.add_argument("--apply", action="store_true", help="Write consensus params to config/local.yaml")
    args = parser.parse_args()

    log = setup_logging()
    cfg = load_config()
    base_params = get_strategy_params(args.strategy)
    param_grid = GRIDS[args.grid]
    tickers = ASSETS[: args.limit] if args.limit else ASSETS

    raw_dfs = load_raw_kline_cache(tickers)
    if not raw_dfs:
        log.error("No cached klines. Run: python run_daily.py")
        return 1

    from services.training_engine.wfo import collect_trading_dates, generate_rolling_folds
    from services.training_engine.wfo import build_ticker_candles

    probe = build_ticker_candles(raw_dfs, base_params)
    dates = collect_trading_dates(probe)
    folds = generate_rolling_folds(
        dates,
        train_bars=args.train_bars,
        test_bars=args.test_bars,
        step_bars=args.step_bars,
    )
    if args.folds and args.folds < len(folds):
        folds = folds[: args.folds]

    total_combos = combo_count(param_grid)
    log.info(
        "WFO [%s]: %d tickers, %d dates, %d folds, %d param combos",
        args.grid,
        len(raw_dfs),
        len(dates),
        len(folds),
        total_combos,
    )

    result = run_walk_forward(
        raw_dfs,
        args.strategy,
        base_params,
        param_grid,
        folds=folds,
        objective=args.objective,
        max_combos=args.max_combos,
        initial_equity=float(cfg.get("initial_equity", 100000)),
        max_positions=int(TRADING_CFG.get("max_positions", 10)),
        slippage_bps=float(TRADING_CFG.get("slippage_bps", 5)),
        commission=float(TRADING_CFG.get("commission", 1.0)),
        regime_cfg=TRADING_CFG.get("regime", {}),
    )

    if "error" in result and not result.get("fold_results"):
        log.error(result["error"])
        return 1

    result["grid"] = args.grid
    log.info(
        "WFO complete: folds=%d avg_oos_sharpe=%.2f avg_oos_dd=%.1f%% consensus=%s",
        result.get("folds", 0),
        result.get("avg_oos_sharpe", 0),
        result.get("avg_oos_max_drawdown_pct", 0),
        result.get("consensus_params", {}),
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    log.info("Wrote %s", args.output)

    if args.apply and result.get("consensus_params"):
        _apply_params_to_local_yaml(args.strategy, result["consensus_params"], log)

    print(
        json.dumps(
            {
                "grid": args.grid,
                "folds": result.get("folds"),
                "param_combos": result.get("param_combos"),
                "avg_oos_sharpe": result.get("avg_oos_sharpe"),
                "consensus_params": result.get("consensus_params"),
                "output": args.output,
            },
            indent=2,
        )
    )
    return 0


def _apply_params_to_local_yaml(strategy: str, params: dict, log):
    import yaml
    from pathlib import Path

    path = Path("config/local.yaml")
    if not path.exists():
        log.warning("config/local.yaml not found; copy config/equity.yaml.example first")
        return

    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    cfg.setdefault("strategies", {})
    cfg["strategies"].setdefault(strategy, {})
    cfg["strategies"][strategy].update(params)

    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)
    log.info("Updated %s strategies.%s with consensus params", path, strategy)


if __name__ == "__main__":
    sys.exit(main())
