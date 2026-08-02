from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from trading_bot.features.indicators import add_all_indicators


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeSignal:
    signal: Signal
    confidence: float
    reason: str


class SignalGenerator:
    """Combines an ML direction probability with technical trend/momentum filters.

    The ML model provides the primary edge; technical filters act as a sanity check
    so the bot doesn't buy strength into an overbought spike or sell into an
    oversold dip against a strong long-term trend.
    """

    def __init__(self, min_probability: float = 0.55, rsi_overbought: float = 70,
                 rsi_oversold: float = 30):
        self.min_probability = min_probability
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold

    def generate(self, raw_df: pd.DataFrame, probability_up: float) -> TradeSignal:
        enriched = add_all_indicators(raw_df).dropna(subset=["sma_200", "rsi_14"])
        if enriched.empty:
            return TradeSignal(Signal.HOLD, probability_up, "insufficient history for filters")

        latest = enriched.iloc[-1]
        uptrend = latest["close"] > latest["sma_200"]
        rsi = latest["rsi_14"]

        if probability_up >= self.min_probability:
            if not uptrend:
                return TradeSignal(Signal.HOLD, probability_up, "bullish ML signal but below SMA200 trend filter")
            if rsi >= self.rsi_overbought:
                return TradeSignal(Signal.HOLD, probability_up, f"bullish ML signal but RSI overbought ({rsi:.1f})")
            return TradeSignal(Signal.BUY, probability_up, f"ML prob_up={probability_up:.2f}, uptrend, RSI={rsi:.1f}")

        if probability_up <= (1 - self.min_probability):
            if uptrend and rsi <= self.rsi_oversold:
                return TradeSignal(Signal.HOLD, probability_up,
                                    f"bearish ML signal but RSI oversold ({rsi:.1f}) within uptrend")
            return TradeSignal(Signal.SELL, probability_up, f"ML prob_down={1 - probability_up:.2f}, RSI={rsi:.1f}")

        return TradeSignal(Signal.HOLD, probability_up, "ML confidence below threshold")
