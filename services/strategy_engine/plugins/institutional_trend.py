from services.strategy_engine.base import StrategyPlugin
from services.strategy_engine.candle_patterns import is_bullish_rejection
from services.strategy_engine.registry import register


def _valid(c: dict, *keys) -> bool:
    return all(c.get(k) is not None for k in keys)


def _regime_ok(c: dict, params: dict) -> bool:
    rsi_min = float(params.get("rsi_regime_min", 45))
    rsi_max = float(params.get("rsi_regime_max", 65))
    if not _valid(c, "close", "sma200", "sma50", "ema10", "ema20", "macd_hist", "rsi14"):
        return False
    stack = (
        c["close"] > c["sma200"]
        and c["sma50"] > c["sma200"]
        and c["ema10"] > c["ema20"] > c["sma50"] > c["sma200"]
        and c["macd_hist"] >= 0
        and rsi_min <= c["rsi14"] <= rsi_max
    )
    return stack


def _macd_signal_rising(current: dict, previous: dict) -> bool:
    if not _valid(current, "macd_signal") or not _valid(previous, "macd_signal"):
        return False
    return current["macd_signal"] > previous["macd_signal"]


def _macd_cross_down(current: dict, previous: dict) -> bool:
    if not _valid(current, "macd_line", "macd_signal") or not _valid(previous, "macd_line", "macd_signal"):
        return False
    return (
        previous["macd_line"] > previous["macd_signal"]
        and current["macd_line"] < current["macd_signal"]
    )


@register
class InstitutionalTrendStrategy(StrategyPlugin):
    name = "InstitutionalTrend"
    description = (
        "Daily large-cap trend: 200 SMA regime, MA stack, EMA pullback entries, "
        "RSI/MACD confirmation"
    )
    default_params = {
        "ema_fast": 10,
        "ema_slow": 20,
        "rsi_len": 14,
        "atr_len": 14,
        "rsi_regime_min": 45,
        "rsi_regime_max": 65,
        "rsi_entry_max": 70,
        "rsi_exhaustion": 75,
        "rsi_exhaustion_drop": 65,
    }
    requires_candles = True

    def signal(self, prices, params=None, candles=None):
        params = params or self.default_params
        if not candles or len(candles) < 2:
            return "HOLD"

        current = candles[-1]
        previous = candles[-2]

        if self._exit_signal(current, previous, params):
            return "SELL"

        if self._entry_signal(current, previous, params):
            return "BUY"

        return "HOLD"

    def _entry_signal(self, current: dict, previous: dict, params: dict) -> bool:
        if not _regime_ok(current, params):
            return False
        if not _valid(current, "low", "ema20", "ema_slow", "volume", "vol_sma20", "rsi14"):
            return False

        pullback = current["low"] <= current["ema20"] or current["low"] <= current.get("ema_slow", current["ema20"])
        if not pullback:
            return False

        return (
            is_bullish_rejection(current, previous)
            and current["volume"] > current["vol_sma20"]
            and current["rsi14"] < float(params.get("rsi_entry_max", 70))
            and _macd_signal_rising(current, previous)
        )

    def _exit_signal(self, current: dict, previous: dict, params: dict) -> bool:
        if not _valid(current, "close", "sma50", "sma200", "ema20", "sma50", "rsi14"):
            return False

        if current["close"] < current["sma50"]:
            return True
        if _macd_cross_down(current, previous):
            return True

        rsi_exhaust = float(params.get("rsi_exhaustion", 75))
        rsi_drop = float(params.get("rsi_exhaustion_drop", 65))
        if previous.get("rsi14") is not None:
            if previous["rsi14"] > rsi_exhaust and current["rsi14"] < rsi_drop:
                return True

        if current["close"] < current["sma200"]:
            return True
        if current["ema20"] < current["sma50"]:
            return True
        return False
