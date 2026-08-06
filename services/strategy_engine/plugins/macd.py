from services.strategy_engine.base import StrategyPlugin
from services.strategy_engine.registry import register


def _ema(series, span):
    k = 2 / (span + 1)
    e = series[0]
    for v in series[1:]:
        e = v * k + e * (1 - k)
    return e


@register
class MacdStrategy(StrategyPlugin):
    name = "MACD"
    description = "MACD line vs signal line crossover"
    default_params = {"fast": 12, "slow": 26, "signal": 9}

    def signal(self, prices, params=None, candles=None):
        params = params or self.default_params
        fast = int(params["fast"])
        slow = int(params["slow"])
        signal = int(params["signal"])
        if len(prices) < slow + signal:
            return "HOLD"

        macd_line = []
        for i in range(len(prices)):
            if i + 1 < slow:
                macd_line.append(0)
            else:
                fast_ema = _ema(prices[max(0, i - fast + 1) : i + 1], fast)
                slow_ema = _ema(prices[max(0, i - slow + 1) : i + 1], slow)
                macd_line.append(fast_ema - slow_ema)

        sig_line = []
        for i in range(len(macd_line)):
            if i + 1 < signal:
                sig_line.append(0)
            else:
                sig_line.append(_ema(macd_line[max(0, i - signal + 1) : i + 1], signal))

        if macd_line[-1] > sig_line[-1]:
            return "BUY"
        if macd_line[-1] < sig_line[-1]:
            return "SELL"
        return "HOLD"
