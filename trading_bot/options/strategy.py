from __future__ import annotations

from dataclasses import dataclass

from trading_bot.strategy.signals import Signal, TradeSignal


@dataclass
class OptionsTradeIntent:
    right: str | None  # "call" | "put" | None (no trade)
    reason: str


def signal_to_option_intent(trade_signal: TradeSignal) -> OptionsTradeIntent:
    """Maps the existing ML+technical equity signal onto a directional options
    trade: bullish -> long call, bearish -> long put, otherwise no trade."""
    if trade_signal.signal == Signal.BUY:
        return OptionsTradeIntent("call", trade_signal.reason)
    if trade_signal.signal == Signal.SELL:
        return OptionsTradeIntent("put", trade_signal.reason)
    return OptionsTradeIntent(None, trade_signal.reason)
