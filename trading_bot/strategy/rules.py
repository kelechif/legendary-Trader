"""Indicator-only trading strategies — no ML model, no training.

Each strategy reads a single indicator-enriched bar (a row from
`add_all_indicators(raw_df)`) and returns a directional BUY/SELL/HOLD state,
the same `TradeSignal` shape the ML `SignalGenerator` produces. That shared
shape is what lets `RuleBacktester` (trading_bot/backtest/strategy_engine.py)
drive any of these with the same position/risk/exit mechanics used for the
ML strategy, so results are directly comparable across strategies.

These are intentionally simple, well-known indicator rules — not curve-fit
to any ticker — so a strategy sweep can show which *style* (trend-following,
mean-reversion, momentum) tends to fit a given ticker's behavior.
"""
from __future__ import annotations

import pandas as pd

from trading_bot.strategy.signals import Signal, TradeSignal


class RuleStrategy:
    """Base class for indicator-only strategies. Subclasses set `name` and
    implement `signal`."""

    name: str = "rule"

    def signal(self, row: pd.Series) -> TradeSignal:
        raise NotImplementedError


class SmaCrossoverStrategy(RuleStrategy):
    """Short-term trend-following: long while the 20-day SMA is above the
    50-day SMA, flat otherwise."""

    name = "SMA 20/50 crossover"

    def signal(self, row: pd.Series) -> TradeSignal:
        fast, slow = row.get("sma_20"), row.get("sma_50")
        if pd.isna(fast) or pd.isna(slow):
            return TradeSignal(Signal.HOLD, 0.5, "insufficient history for SMA 20/50")
        if fast > slow:
            return TradeSignal(Signal.BUY, 0.6, f"SMA20 {fast:.2f} > SMA50 {slow:.2f}")
        return TradeSignal(Signal.SELL, 0.6, f"SMA20 {fast:.2f} <= SMA50 {slow:.2f}")


class SmaGoldenCrossStrategy(RuleStrategy):
    """Longer-term trend-following: the classic golden/death cross, long
    while the 50-day SMA is above the 200-day SMA."""

    name = "SMA 50/200 golden cross"

    def signal(self, row: pd.Series) -> TradeSignal:
        fast, slow = row.get("sma_50"), row.get("sma_200")
        if pd.isna(fast) or pd.isna(slow):
            return TradeSignal(Signal.HOLD, 0.5, "insufficient history for SMA 50/200")
        if fast > slow:
            return TradeSignal(Signal.BUY, 0.6, f"SMA50 {fast:.2f} > SMA200 {slow:.2f}")
        return TradeSignal(Signal.SELL, 0.6, f"SMA50 {fast:.2f} <= SMA200 {slow:.2f}")


class RsiMeanReversionStrategy(RuleStrategy):
    """Classic mean-reversion: buy oversold, sell overbought, hold through
    the middle (the engine's ATR stop/target can still exit in between)."""

    name = "RSI(14) mean reversion"

    def __init__(self, oversold: float = 30.0, overbought: float = 70.0):
        self.oversold = oversold
        self.overbought = overbought

    def signal(self, row: pd.Series) -> TradeSignal:
        rsi = row.get("rsi_14")
        if pd.isna(rsi):
            return TradeSignal(Signal.HOLD, 0.5, "insufficient history for RSI")
        if rsi <= self.oversold:
            return TradeSignal(Signal.BUY, 0.65, f"RSI {rsi:.1f} <= {self.oversold:.0f} (oversold)")
        if rsi >= self.overbought:
            return TradeSignal(Signal.SELL, 0.65, f"RSI {rsi:.1f} >= {self.overbought:.0f} (overbought)")
        return TradeSignal(Signal.HOLD, 0.5, f"RSI {rsi:.1f} neutral")


class MacdCrossoverStrategy(RuleStrategy):
    """Momentum: long while the MACD line is above its signal line."""

    name = "MACD crossover"

    def signal(self, row: pd.Series) -> TradeSignal:
        macd_line, signal_line = row.get("macd"), row.get("macd_signal")
        if pd.isna(macd_line) or pd.isna(signal_line):
            return TradeSignal(Signal.HOLD, 0.5, "insufficient history for MACD")
        if macd_line > signal_line:
            return TradeSignal(Signal.BUY, 0.6, f"MACD {macd_line:.3f} > signal {signal_line:.3f}")
        return TradeSignal(Signal.SELL, 0.6, f"MACD {macd_line:.3f} <= signal {signal_line:.3f}")


class BollingerReversionStrategy(RuleStrategy):
    """Mean-reversion off the Bollinger Bands: buy at/below the lower band,
    sell at/above the upper band, hold in between."""

    name = "Bollinger Band reversion"

    def signal(self, row: pd.Series) -> TradeSignal:
        close, lower, upper = row.get("close"), row.get("bb_lower"), row.get("bb_upper")
        if pd.isna(close) or pd.isna(lower) or pd.isna(upper):
            return TradeSignal(Signal.HOLD, 0.5, "insufficient history for Bollinger Bands")
        if close <= lower:
            return TradeSignal(Signal.BUY, 0.6, f"close {close:.2f} <= lower band {lower:.2f}")
        if close >= upper:
            return TradeSignal(Signal.SELL, 0.6, f"close {close:.2f} >= upper band {upper:.2f}")
        return TradeSignal(Signal.HOLD, 0.5, "inside the bands")


class BuyAndHoldStrategy(RuleStrategy):
    """Baseline: buy on the first bar it sees, then never sell on signal
    (only the engine's own stop/target — if triggered — would exit). Useful
    as a reference for whether an active strategy is actually adding value."""

    name = "Buy & hold"

    def __init__(self) -> None:
        self._bought = False

    def signal(self, row: pd.Series) -> TradeSignal:
        if not self._bought:
            self._bought = True
            return TradeSignal(Signal.BUY, 1.0, "buy & hold baseline: initial entry")
        return TradeSignal(Signal.HOLD, 1.0, "buy & hold baseline: holding")
