"""Run every strategy against every ticker and report the best fit per
ticker. Ties together the ML strategy (`BacktestEngine`) and the
indicator-only strategies (`RuleBacktester`) under one comparable table,
since both report the same `BacktestMetrics` over the same held-out window.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from trading_bot.backtest.engine import BacktestEngine
from trading_bot.backtest.strategy_engine import RuleBacktester
from trading_bot.data.fetcher import DataFetcher
from trading_bot.logger import get_logger
from trading_bot.ml.model import DirectionModel
from trading_bot.strategy.risk import RiskManager, RiskParams
from trading_bot.strategy.rules import (
    BollingerReversionStrategy,
    BuyAndHoldStrategy,
    MacdCrossoverStrategy,
    RsiMeanReversionStrategy,
    RuleStrategy,
    SmaCrossoverStrategy,
    SmaGoldenCrossStrategy,
)
from trading_bot.strategy.signals import SignalGenerator

logger = get_logger(__name__)

ML_STRATEGY = "ml_trend"

# name -> zero-arg factory. A factory (not a shared instance) because some
# strategies (buy_and_hold) carry per-run state.
RULE_STRATEGIES: dict[str, Callable[[], RuleStrategy]] = {
    "sma_20_50": SmaCrossoverStrategy,
    "sma_50_200": SmaGoldenCrossStrategy,
    "rsi_mean_reversion": RsiMeanReversionStrategy,
    "macd_crossover": MacdCrossoverStrategy,
    "bollinger_reversion": BollingerReversionStrategy,
    "buy_and_hold": BuyAndHoldStrategy,
}

ALL_STRATEGIES: list[str] = [ML_STRATEGY, *RULE_STRATEGIES.keys()]

STRATEGY_LABELS: dict[str, str] = {
    ML_STRATEGY: "ML trend (model + SMA200/RSI filter)",
    **{key: factory.name for key, factory in RULE_STRATEGIES.items()},
}

RESULT_COLUMNS = [
    "symbol", "strategy", "total_return_pct", "cagr_pct", "sharpe_ratio",
    "max_drawdown_pct", "win_rate_pct", "num_trades", "final_equity", "error",
]


@dataclass
class SweepRow:
    symbol: str
    strategy: str
    total_return_pct: float = float("nan")
    cagr_pct: float = float("nan")
    sharpe_ratio: float = float("nan")
    max_drawdown_pct: float = float("nan")
    win_rate_pct: float = float("nan")
    num_trades: int = 0
    final_equity: float = float("nan")
    error: str | None = None


def run_sweep(
    symbols: list[str],
    config: dict,
    strategy_names: list[str] | None = None,
    period: str | None = None,
) -> pd.DataFrame:
    """Backtest every (symbol, strategy) pair and return a long-format
    DataFrame — one row per pair, `RESULT_COLUMNS` wide. Fetches each
    symbol's history once and reuses it across all its strategies. A failure
    on one (symbol, strategy) pair — bad ticker, not enough history — is
    recorded as an error row rather than aborting the sweep.
    """
    strategy_names = strategy_names or ALL_STRATEGIES
    data_cfg, model_cfg = config["data"], config["model"]
    period = period or data_cfg["history_period"]

    fetcher = DataFetcher()
    risk_manager = RiskManager(RiskParams(**config["risk"]))
    ml_engine = BacktestEngine(
        starting_cash=config["backtest"]["starting_cash"],
        commission_per_share=config["backtest"]["commission_per_share"],
        slippage_pct=config["backtest"]["slippage_pct"],
    )
    rule_engine = RuleBacktester(
        starting_cash=config["backtest"]["starting_cash"],
        commission_per_share=config["backtest"]["commission_per_share"],
        slippage_pct=config["backtest"]["slippage_pct"],
        test_split=model_cfg["train_test_split"],
    )

    rows: list[SweepRow] = []
    for symbol in symbols:
        try:
            raw_df = fetcher.fetch(symbol, period=period, interval=data_cfg["interval"])
        except Exception as exc:  # noqa: BLE001 - one bad symbol shouldn't kill the sweep
            logger.warning("Sweep: could not fetch %s: %s", symbol, exc)
            rows.extend(SweepRow(symbol, name, error=str(exc)) for name in strategy_names)
            continue

        for name in strategy_names:
            try:
                if name == ML_STRATEGY:
                    model = DirectionModel(
                        model_type=model_cfg["type"], n_estimators=model_cfg["n_estimators"],
                        max_depth=model_cfg["max_depth"], lookahead_bars=model_cfg["lookahead_bars"],
                        up_threshold_pct=model_cfg["up_threshold_pct"],
                        train_test_split=model_cfg["train_test_split"],
                    )
                    signal_generator = SignalGenerator(min_probability=model_cfg["min_probability"])
                    result = ml_engine.run(raw_df, model, signal_generator, risk_manager)
                else:
                    strategy = RULE_STRATEGIES[name]()
                    result = rule_engine.run(raw_df, strategy, risk_manager)

                m = result.metrics
                rows.append(SweepRow(
                    symbol=symbol, strategy=name, total_return_pct=m.total_return_pct,
                    cagr_pct=m.cagr_pct, sharpe_ratio=m.sharpe_ratio, max_drawdown_pct=m.max_drawdown_pct,
                    win_rate_pct=m.win_rate_pct, num_trades=m.num_trades, final_equity=m.final_equity,
                ))
            except Exception as exc:  # noqa: BLE001 - one bad pair shouldn't kill the sweep
                logger.warning("Sweep failed for %s / %s: %s", symbol, name, exc)
                rows.append(SweepRow(symbol, name, error=str(exc)))

    return pd.DataFrame([vars(r) for r in rows], columns=RESULT_COLUMNS)


def best_per_symbol(results: pd.DataFrame, metric: str = "sharpe_ratio") -> pd.DataFrame:
    """The best-performing strategy per symbol by `metric` (higher is
    better), dropping symbol/strategy pairs that errored out. Empty input (or
    all-error input) returns an empty frame with the same columns."""
    ok = results[results["error"].isna()].copy()
    if ok.empty:
        return ok
    best_idx = ok.groupby("symbol")[metric].idxmax()
    return ok.loc[best_idx].sort_values(metric, ascending=False).reset_index(drop=True)
