import unittest

from prop_algo.core.adapters.mock_adapter import MockAdapter
from prop_algo.core.registry.registry import Registry
from prop_algo.trading.autopilot.autopilot_engine import AutopilotEngine
from prop_algo.trading.execution.execution_optimizer import ExecutionOptimizer
from prop_algo.trading.multi_account.manager import MultiAccountManager


def test_execution():
    r = Registry()
    r.register_account("A", MockAdapter("A"))
    exec = ExecutionOptimizer(r)
    signals = {("A", "EURUSD"): {"trend": {"signal": "BUY"}}}
    risk = {"A": 1.0}
    res = exec.run(signals, risk)
    assert len(res) > 0


class TestExecution(unittest.TestCase):
    def test_execution(self):
        test_execution()

    def test_run_skips_low_risk_factor(self):
        r = Registry()
        r.register_account("A", MockAdapter("A"))
        opt = ExecutionOptimizer(r)
        signals = {("A", "EURUSD"): {"trend": {"signal": "BUY"}}}
        self.assertEqual(opt.run(signals, {"A": 0.2}), [])

    def test_multi_account_broadcast(self):
        r = Registry()
        r.register_account("A", MockAdapter("A"))
        r.register_account("B", MockAdapter("B"))
        mgr = MultiAccountManager(r)
        results = mgr.broadcast(
            {"symbol": "EURUSD", "size": 0.1, "sl": None, "tp": None}
        )
        self.assertEqual(len(results), 2)
        self.assertTrue(all(row["status"] == "FILLED" for row in results))

    def test_autopilot_should_trade(self):
        self.assertTrue(AutopilotEngine().should_trade())


if __name__ == "__main__":
    unittest.main()
