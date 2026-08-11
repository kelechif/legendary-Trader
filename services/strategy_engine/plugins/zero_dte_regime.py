"""Regime gate for 0DTE — mirrors TradeWithMeNow CTV filters in Python."""

from services.strategy_engine.base import StrategyPlugin
from services.strategy_engine.registry import register


def _in_window(time_hhmm: int, start: int, end: int) -> bool:
    return start <= time_hhmm <= end


@register
class ZeroDTERegimeStrategy(StrategyPlugin):
    name = "ZeroDTERegime"
    description = "0DTE regime gate: time windows + trend/VIX proxy for CTV entries"
    default_params = {
        "morning_start": 945,
        "morning_end": 1015,
        "afternoon_start": 1430,
        "afternoon_end": 1515,
        "use_morning": True,
        "use_afternoon": True,
        "vix_max": 28.0,
        "sma_regime": 50,
    }
    requires_candles = True

    def signal(self, prices, params=None, candles=None):
        params = params or self.default_params
        if not candles or len(candles) < 6:
            return "HOLD"

        c = candles[-1]
        close = c.get("close")
        if close is None:
            return "HOLD"

        sma_len = int(params.get("sma_regime", 50))
        if len(candles) < sma_len:
            return "HOLD"

        sma = sum(x["close"] for x in candles[-sma_len:]) / sma_len
        shift = 1 if close > candles[-6]["close"] else (-1 if close < candles[-6]["close"] else 0)
        regime = 1 if close > sma else (-1 if close < sma else 0)

        t = int(c.get("time_hhmm", 1000))
        in_window = (
            (params.get("use_morning") and _in_window(t, params["morning_start"], params["morning_end"]))
            or (params.get("use_afternoon") and _in_window(t, params["afternoon_start"], params["afternoon_end"]))
        )
        if not in_window or t <= 944 or t >= 1555:
            return "HOLD"

        vix = c.get("vix")
        if vix is not None and float(vix) > float(params.get("vix_max", 28)):
            return "HOLD"

        aligned = (shift == 1 and regime >= 0) or (shift == -1 and regime <= 0)
        if not aligned or shift == 0:
            return "HOLD"

        return "BUY" if shift == 1 else "SELL"
