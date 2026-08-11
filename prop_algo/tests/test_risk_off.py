import unittest

from prop_algo.trading.risk_off.risk_off_engine import RiskOffEngine


def test_risk_off():
    engine = RiskOffEngine()
    factor, _ = engine.compute({"equity": 10000, "balance": 10000}, None)
    assert factor == 1.0


class TestRiskOff(unittest.TestCase):
    def test_risk_off(self):
        test_risk_off()

    def test_drawdown_scales_down(self):
        engine = RiskOffEngine()
        factor, meta = engine.compute({"equity": 9890, "balance": 10000}, None)
        self.assertEqual(factor, 0.2)
        self.assertEqual(meta["reason"], "drawdown")


if __name__ == "__main__":
    unittest.main()
