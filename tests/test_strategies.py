"""Tests for the indicator-only strategies, the rule-based backtester, and
the strategy sweep (best strategy per ticker)."""
from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.backtest.strategy_engine import RuleBacktester
from trading_bot.backtest.sweep import ALL_STRATEGIES, ML_STRATEGY, RULE_STRATEGIES, best_per_symbol, run_sweep
from trading_bot.strategy.risk import RiskManager, RiskParams
from trading_bot.strategy.rules import (
    BollingerReversionStrategy,
    BuyAndHoldStrategy,
    MacdCrossoverStrategy,
    RsiMeanReversionStrategy,
    SmaCrossoverStrategy,
    SmaGoldenCrossStrategy,
)
from trading_bot.strategy.signals import Signal
from tests.utils import make_synthetic_ohlcv

MODEL_CFG = {
    "type": "random_forest", "n_estimators": 20, "max_depth": 3,
    "lookahead_bars": 1, "up_threshold_pct": 0.0, "train_test_split": 0.8,
    "min_probability": 0.55,
}
RISK_CFG = {
    "risk_per_trade_pct": 0.01, "stop_loss_atr_mult": 2.0, "take_profit_atr_mult": 3.0,
    "max_position_pct": 0.25, "max_open_positions": 5, "daily_loss_limit_pct": 0.03,
}


def _sweep_config():
    return {
        "data": {"interval": "1d", "history_period": "2y"},
        "model": MODEL_CFG,
        "risk": RISK_CFG,
        "backtest": {"starting_cash": 100_000, "commission_per_share": 0.0, "slippage_pct": 0.0005},
    }


# ---------------------------------------------------------------------------
# Rule strategy signal logic
# ---------------------------------------------------------------------------

def test_sma_crossover_buys_above_and_sells_below():
    strat = SmaCrossoverStrategy()
    above = pd.Series({"sma_20": 110.0, "sma_50": 100.0})
    below = pd.Series({"sma_20": 90.0, "sma_50": 100.0})
    assert strat.signal(above).signal == Signal.BUY
    assert strat.signal(below).signal == Signal.SELL


def test_sma_golden_cross_holds_on_missing_history():
    strat = SmaGoldenCrossStrategy()
    row = pd.Series({"sma_50": 100.0, "sma_200": float("nan")})
    assert strat.signal(row).signal == Signal.HOLD


def test_rsi_mean_reversion_buys_oversold_sells_overbought_holds_neutral():
    strat = RsiMeanReversionStrategy()
    assert strat.signal(pd.Series({"rsi_14": 20.0})).signal == Signal.BUY
    assert strat.signal(pd.Series({"rsi_14": 80.0})).signal == Signal.SELL
    assert strat.signal(pd.Series({"rsi_14": 50.0})).signal == Signal.HOLD


def test_macd_crossover_tracks_line_vs_signal():
    strat = MacdCrossoverStrategy()
    bullish = pd.Series({"macd": 1.5, "macd_signal": 1.0})
    bearish = pd.Series({"macd": 0.5, "macd_signal": 1.0})
    assert strat.signal(bullish).signal == Signal.BUY
    assert strat.signal(bearish).signal == Signal.SELL


def test_bollinger_reversion_buys_lower_sells_upper_holds_inside():
    strat = BollingerReversionStrategy()
    at_lower = pd.Series({"close": 95.0, "bb_lower": 96.0, "bb_upper": 105.0})
    at_upper = pd.Series({"close": 106.0, "bb_lower": 95.0, "bb_upper": 105.0})
    inside = pd.Series({"close": 100.0, "bb_lower": 95.0, "bb_upper": 105.0})
    assert strat.signal(at_lower).signal == Signal.BUY
    assert strat.signal(at_upper).signal == Signal.SELL
    assert strat.signal(inside).signal == Signal.HOLD


def test_buy_and_hold_buys_once_then_holds():
    strat = BuyAndHoldStrategy()
    row = pd.Series({"close": 100.0})
    assert strat.signal(row).signal == Signal.BUY
    assert strat.signal(row).signal == Signal.HOLD
    assert strat.signal(row).signal == Signal.HOLD


# ---------------------------------------------------------------------------
# RuleBacktester
# ---------------------------------------------------------------------------

def test_rule_backtester_runs_end_to_end_for_every_strategy():
    df = make_synthetic_ohlcv(n=500)
    risk_manager = RiskManager(RiskParams())
    engine = RuleBacktester(starting_cash=100_000, test_split=0.8)

    for factory in RULE_STRATEGIES.values():
        result = engine.run(df, factory(), risk_manager)
        assert len(result.equity_curve) > 0
        assert result.metrics.final_equity > 0
        assert isinstance(result.metrics.num_trades, int)


def test_rule_backtester_rejects_too_little_history():
    df = make_synthetic_ohlcv(n=20)
    engine = RuleBacktester(test_split=0.8)
    with pytest.raises(ValueError):
        engine.run(df, SmaCrossoverStrategy(), RiskManager(RiskParams()))


# ---------------------------------------------------------------------------
# Sweep + best_per_symbol
# ---------------------------------------------------------------------------

def test_run_sweep_covers_every_symbol_strategy_pair(monkeypatch):
    monkeypatch.setattr(
        "trading_bot.data.fetcher.DataFetcher.fetch",
        lambda self, symbol, period="2y", interval="1d": make_synthetic_ohlcv(n=500, seed=hash(symbol) % 1000),
    )

    results = run_sweep(["AAPL", "MSFT"], _sweep_config(), strategy_names=["sma_20_50", "buy_and_hold", ML_STRATEGY])

    assert len(results) == 2 * 3
    assert set(results["symbol"]) == {"AAPL", "MSFT"}
    assert set(results["strategy"]) == {"sma_20_50", "buy_and_hold", ML_STRATEGY}
    assert results["error"].isna().all()


def test_run_sweep_records_error_without_aborting_other_symbols(monkeypatch):
    def fake_fetch(self, symbol, period="2y", interval="1d"):
        if symbol == "BADTICKER":
            raise ValueError("No data returned for symbol 'BADTICKER'")
        return make_synthetic_ohlcv(n=500)

    monkeypatch.setattr("trading_bot.data.fetcher.DataFetcher.fetch", fake_fetch)

    results = run_sweep(["BADTICKER", "AAPL"], _sweep_config(), strategy_names=["sma_20_50", "buy_and_hold"])

    bad_rows = results[results["symbol"] == "BADTICKER"]
    good_rows = results[results["symbol"] == "AAPL"]
    assert len(bad_rows) == 2
    assert bad_rows["error"].notna().all()
    assert len(good_rows) == 2
    assert good_rows["error"].isna().all()


def test_best_per_symbol_picks_the_highest_metric_and_drops_errors():
    results = pd.DataFrame([
        {"symbol": "AAPL", "strategy": "sma_20_50", "sharpe_ratio": 0.5, "error": None},
        {"symbol": "AAPL", "strategy": "buy_and_hold", "sharpe_ratio": 1.2, "error": None},
        {"symbol": "MSFT", "strategy": "sma_20_50", "sharpe_ratio": 0.9, "error": None},
        {"symbol": "MSFT", "strategy": "buy_and_hold", "sharpe_ratio": None, "error": "boom"},
    ])

    best = best_per_symbol(results, metric="sharpe_ratio")

    assert dict(zip(best["symbol"], best["strategy"])) == {"AAPL": "buy_and_hold", "MSFT": "sma_20_50"}


def test_best_per_symbol_empty_when_everything_errors():
    results = pd.DataFrame([{"symbol": "AAPL", "strategy": "sma_20_50", "sharpe_ratio": None, "error": "boom"}])
    assert best_per_symbol(results).empty


def test_all_strategies_have_labels():
    from trading_bot.backtest.sweep import STRATEGY_LABELS
    assert set(STRATEGY_LABELS) == set(ALL_STRATEGIES)
    assert all(isinstance(label, str) and label for label in STRATEGY_LABELS.values())
