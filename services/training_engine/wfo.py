"""Walk-forward optimization over universe backtest."""

from itertools import product
from typing import Iterable

from services.market_data.indicators import compute_indicators, dataframe_to_candles
from services.training_engine.universe_backtest import run_backtest_universe


def _date_key(candle: dict) -> str:
    return str(candle.get("date") or "")


def collect_trading_dates(ticker_candles: dict) -> list[str]:
    dates = set()
    for candles in ticker_candles.values():
        for c in candles:
            d = _date_key(c)
            if d:
                dates.add(d)
    return sorted(dates)


def build_ticker_candles(raw_dfs: dict, params: dict) -> dict:
    """Recompute indicators for each ticker at given params."""
    out = {}
    for ticker, df in raw_dfs.items():
        enriched = compute_indicators(df, params)
        candles = dataframe_to_candles(enriched)
        if candles:
            out[ticker] = candles
    return out


def slice_ticker_candles(
    ticker_candles: dict,
    start_date: str,
    end_date: str,
    warmup: int = 220,
) -> dict:
    """Keep warmup bars before start_date; cap at end_date."""
    out = {}
    for ticker, candles in ticker_candles.items():
        if not candles:
            continue
        capped = [c for c in candles if _date_key(c) <= end_date]
        start_idx = next((i for i, c in enumerate(capped) if _date_key(c) >= start_date), None)
        if start_idx is None:
            continue
        begin = max(0, start_idx - warmup)
        sliced = capped[begin:]
        if len(sliced) >= warmup:
            out[ticker] = sliced
    return out


def expand_param_grid(base_params: dict, grid: dict) -> list[dict]:
    if not grid:
        return [dict(base_params)]
    keys = list(grid.keys())
    combos = []
    for values in product(*(grid[k] for k in keys)):
        params = dict(base_params)
        for k, v in zip(keys, values):
            params[k] = v
        combos.append(params)
    return combos


def objective_score(metrics: dict, objective: str = "sharpe", max_dd_penalty: float = 35.0) -> float:
    if not metrics:
        return float("-inf")
    if metrics.get("total_trades", 0) < 5:
        return float("-inf")

    score = float(metrics.get(objective, 0) or 0)
    if metrics.get("max_drawdown_pct", 0) > max_dd_penalty:
        score -= 2.0
    return score


def generate_rolling_folds(
    dates: list[str],
    train_bars: int = 756,
    test_bars: int = 126,
    step_bars: int = 126,
    min_history: int = 220,
) -> list[dict]:
    """Build rolling IS/OOS windows on shared trading dates."""
    if len(dates) < min_history + train_bars + test_bars:
        return []

    folds = []
    offset = 0
    fold_id = 0
    while offset + train_bars + test_bars <= len(dates):
        is_start = dates[offset]
        is_end = dates[offset + train_bars - 1]
        oos_start = dates[offset + train_bars]
        oos_end = dates[offset + train_bars + test_bars - 1]
        folds.append(
            {
                "fold": fold_id,
                "is_start": is_start,
                "is_end": is_end,
                "oos_start": oos_start,
                "oos_end": oos_end,
            }
        )
        fold_id += 1
        offset += step_bars
    return folds


def run_wfo_fold(
    raw_dfs: dict,
    strategy: str,
    param_combos: list[dict],
    is_start: str,
    is_end: str,
    oos_start: str,
    oos_end: str,
    objective: str = "sharpe",
    warmup: int = 220,
    **backtest_kwargs,
) -> dict:
    """Optimize on IS window, validate best params on OOS window."""
    best_params = None
    best_score = float("-inf")
    best_is = None
    trials = []

    for i, params in enumerate(param_combos):
        full = build_ticker_candles(raw_dfs, params)
        is_data = slice_ticker_candles(full, is_start, is_end, warmup=warmup)
        if not is_data:
            continue
        result = run_backtest_universe(is_data, strategy, params=params, min_warmup=warmup, **backtest_kwargs)
        if "error" in result:
            continue
        score = objective_score(result["metrics"], objective=objective)
        trials.append({"params": params, "score": score, "metrics": result["metrics"]})
        if score > best_score:
            best_score = score
            best_params = params
            best_is = result
        if (i + 1) % 10 == 0 or i + 1 == len(param_combos):
            import logging
            logging.getLogger("quant-platform").info(
                "WFO trial %d/%d best_score=%.3f", i + 1, len(param_combos), best_score
            )

    if best_params is None:
        return {"error": "No valid IS trials", "trials": len(trials)}

    oos_full = build_ticker_candles(raw_dfs, best_params)
    oos_data = slice_ticker_candles(oos_full, oos_start, oos_end, warmup=warmup)
    oos_result = run_backtest_universe(
        oos_data, strategy, params=best_params, min_warmup=warmup, **backtest_kwargs
    )

    return {
        "is_start": is_start,
        "is_end": is_end,
        "oos_start": oos_start,
        "oos_end": oos_end,
        "best_params": best_params,
        "is_score": best_score,
        "is_metrics": best_is["metrics"] if best_is else {},
        "oos_metrics": oos_result.get("metrics", {}),
        "oos_trades": len(oos_result.get("trades", [])),
        "trials": len(trials),
    }


def run_walk_forward(
    raw_dfs: dict,
    strategy: str,
    base_params: dict,
    param_grid: dict,
    folds: Iterable[dict] | None = None,
    objective: str = "sharpe",
    warmup: int = 220,
    max_combos: int = 0,
    **backtest_kwargs,
) -> dict:
    """Run rolling WFO folds and aggregate OOS performance."""
    probe = build_ticker_candles(raw_dfs, base_params)
    dates = collect_trading_dates(probe)
    fold_defs = list(folds) if folds else generate_rolling_folds(dates)
    if not fold_defs:
        return {"error": "Not enough history for walk-forward folds", "dates": len(dates)}

    param_combos = expand_param_grid(base_params, param_grid)
    if max_combos and len(param_combos) > max_combos:
        import random

        random.seed(42)
        param_combos = random.sample(param_combos, max_combos)

    fold_results = []

    for fold in fold_defs:
        result = run_wfo_fold(
            raw_dfs,
            strategy,
            param_combos,
            fold["is_start"],
            fold["is_end"],
            fold["oos_start"],
            fold["oos_end"],
            objective=objective,
            warmup=warmup,
            **backtest_kwargs,
        )
        result["fold"] = fold.get("fold", len(fold_results))
        fold_results.append(result)

    valid = [f for f in fold_results if "error" not in f]
    if not valid:
        return {"error": "All WFO folds failed", "fold_results": fold_results}

    oos_sharpes = [f["oos_metrics"].get("sharpe", 0) for f in valid]
    oos_dds = [f["oos_metrics"].get("max_drawdown_pct", 0) for f in valid]
    avg_oos_sharpe = sum(oos_sharpes) / len(oos_sharpes)
    avg_oos_dd = sum(oos_dds) / len(oos_dds)

    # Most frequent winning param values across folds
    param_votes: dict[str, dict] = {}
    for f in valid:
        for k, v in f["best_params"].items():
            param_votes.setdefault(k, {})
            key = str(v)
            param_votes[k][key] = param_votes[k].get(key, 0) + 1

    consensus = {}
    for k, counts in param_votes.items():
        consensus[k] = type(base_params.get(k, list(counts.keys())[0]))(
            max(counts.items(), key=lambda x: x[1])[0]
        )

    return {
        "strategy": strategy,
        "folds": len(valid),
        "param_combos": len(param_combos),
        "objective": objective,
        "fold_results": fold_results,
        "consensus_params": consensus,
        "avg_oos_sharpe": round(avg_oos_sharpe, 4),
        "avg_oos_max_drawdown_pct": round(avg_oos_dd, 2),
        "dates": len(dates),
    }
