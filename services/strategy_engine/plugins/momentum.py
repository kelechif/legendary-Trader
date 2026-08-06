from services.strategy_engine.base import StrategyPlugin
from services.strategy_engine.registry import register


@register
class MomentumStrategy(StrategyPlugin):
    name = "Momentum"
    description = "Trend following based on lookback return"
    default_params = {"lookback": 20, "threshold": 0.002}

    def signal(self, prices, params=None, candles=None):
        params = params or self.default_params
        lookback = int(params["lookback"])
        threshold = float(params["threshold"])
        if len(prices) < lookback + 1:
            return "HOLD"
        ret = (prices[-1] - prices[-lookback]) / prices[-lookback]
        if ret > threshold:
            return "BUY"
        if ret < -threshold:
            return "SELL"
        return "HOLD"
