from .trend_strategy import TrendStrategy
from .breakout_strategy import BreakoutStrategy
from .mean_reversion_strategy import MeanReversionStrategy


class StrategyEngine:
    def __init__(self, registry):
        self.registry = registry
        self.strategies = {
            "trend": TrendStrategy(),
            "breakout": BreakoutStrategy(),
            "mean_rev": MeanReversionStrategy(),
        }

    def run(self, market_data):
        signals = {}
        for key, df in market_data.items():
            acc_signals = {}
            for name, strat in self.strategies.items():
                acc_signals[name] = strat.generate_signals(df)
            signals[key] = acc_signals
        return signals
