from services.strategy_engine.base import StrategyPlugin
from services.strategy_engine.registry import register


@register
class BreakoutStrategy(StrategyPlugin):
    name = "Breakout"
    description = "Breakout above/below recent range"
    default_params = {"lookback": 30, "buffer": 0.0015}

    def signal(self, prices, params=None, candles=None):
        params = params or self.default_params
        lookback = int(params["lookback"])
        buffer = float(params["buffer"])
        if len(prices) < lookback + 1:
            return "HOLD"
        recent = prices[-lookback - 1 : -1]
        high = max(recent)
        low = min(recent)
        last = prices[-1]
        if last > high * (1 + buffer):
            return "BUY"
        if last < low * (1 - buffer):
            return "SELL"
        return "HOLD"
