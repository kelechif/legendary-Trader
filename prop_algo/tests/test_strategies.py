import unittest

import pandas as pd

from prop_algo.core.adapters.mock_adapter import MockAdapter
from prop_algo.core.registry.registry import Registry
from prop_algo.trading.strategies.breakout_strategy import BreakoutStrategy
from prop_algo.trading.strategies.engine import StrategyEngine
from prop_algo.trading.strategies.mean_reversion_strategy import MeanReversionStrategy
from prop_algo.trading.strategies.trend_strategy import TrendStrategy


def test_strategy_engine():
    r = Registry()
    r.register_account("A", MockAdapter("A"))
    engine = StrategyEngine(r)
    data = r.get_all_history()
    signals = engine.run(data)
    assert len(signals) > 0


def _rising_df(n: int = 120, start: float = 100.0) -> pd.DataFrame:
    closes = [start + i for i in range(n)]
    return pd.DataFrame({"close": closes})


class TestStrategies(unittest.TestCase):
    def test_strategy_engine(self):
        test_strategy_engine()

    def test_trend_buy_on_uptrend(self):
        out = TrendStrategy().generate_signals(_rising_df(60))
        self.assertEqual(out["signal"], "BUY")

    def test_trend_sell_on_downtrend(self):
        closes = [100.0 - i for i in range(60)]
        out = TrendStrategy().generate_signals(pd.DataFrame({"close": closes}))
        self.assertEqual(out["signal"], "SELL")

    def test_breakout_hold_when_close_not_above_rolling_high(self):
        df = _rising_df(120)
        self.assertEqual(BreakoutStrategy().generate_signals(df)["signal"], "HOLD")

    def test_mean_reversion_sell_when_above_ma(self):
        out = MeanReversionStrategy().generate_signals(_rising_df(120))
        self.assertEqual(out["signal"], "SELL")

    def test_mean_reversion_buy_when_below_ma(self):
        closes = [100.0 - i for i in range(120)]
        out = MeanReversionStrategy().generate_signals(pd.DataFrame({"close": closes}))
        self.assertEqual(out["signal"], "BUY")


if __name__ == "__main__":
    unittest.main()
