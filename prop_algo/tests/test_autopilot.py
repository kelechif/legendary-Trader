"""Unit tests for AutopilotEngine allow / block / pause behavior."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from prop_algo.core.adapters.mock_adapter import MockAdapter
from prop_algo.core.registry.registry import Registry
from prop_algo.trading.autopilot.autopilot_engine import (
    AutopilotEngine,
    execution_gate,
)
from prop_algo.trading.execution.execution_optimizer import ExecutionOptimizer


class TestAutopilot(unittest.TestCase):
    def test_should_trade_allows_when_enabled(self):
        with mock.patch.dict(os.environ, {"AUTOPILOT_ENABLED": "1"}, clear=False):
            self.assertTrue(AutopilotEngine().should_trade())

    def test_disabled_blocks(self):
        with mock.patch.dict(os.environ, {"AUTOPILOT_ENABLED": "0"}, clear=False):
            engine = AutopilotEngine()
            self.assertFalse(engine.enabled())
            self.assertFalse(engine.should_trade())
            status = engine.evaluate()
            self.assertEqual(status["state"], "off")
            self.assertFalse(status["allow"])
            blocked, reason = execution_gate(status)
            self.assertTrue(blocked)
            self.assertEqual(reason, "autopilot_off")

    def test_env_pause_blocks(self):
        with mock.patch.dict(
            os.environ,
            {"AUTOPILOT_ENABLED": "1", "AUTOPILOT_PAUSED": "1"},
            clear=False,
        ):
            status = AutopilotEngine().evaluate()
            self.assertTrue(status["paused"])
            self.assertFalse(status["allow"])
            self.assertEqual(status["reason"], "paused")
            blocked, reason = execution_gate(status)
            self.assertTrue(blocked)
            self.assertEqual(reason, "autopilot_paused")

    def test_safe_mode_pauses(self):
        with mock.patch.dict(
            os.environ,
            {"AUTOPILOT_ENABLED": "1", "AUTOPILOT_PAUSED": "0"},
            clear=False,
        ):
            status = AutopilotEngine().evaluate(unified_mode="SAFE_MODE")
            self.assertTrue(status["paused"])
            self.assertEqual(status["reason"], "SAFE_MODE")
            self.assertFalse(AutopilotEngine().should_trade(unified_mode="SAFE_MODE"))

    def test_halt_pauses(self):
        with mock.patch.dict(
            os.environ,
            {"AUTOPILOT_ENABLED": "1", "AUTOPILOT_PAUSED": "0"},
            clear=False,
        ):
            status = AutopilotEngine().evaluate(gov_mode="HALT")
            self.assertTrue(status["paused"])
            self.assertEqual(status["reason"], "HALT")

    def test_risk_off_active_pauses(self):
        with mock.patch.dict(
            os.environ,
            {"AUTOPILOT_ENABLED": "1", "AUTOPILOT_PAUSED": "0"},
            clear=False,
        ):
            status = AutopilotEngine().evaluate(
                {"active": True, "reason": "drawdown"}
            )
            self.assertTrue(status["paused"])
            self.assertEqual(status["reason"], "drawdown")

    def test_normal_allows(self):
        with mock.patch.dict(
            os.environ,
            {"AUTOPILOT_ENABLED": "1", "AUTOPILOT_PAUSED": "0"},
            clear=False,
        ):
            status = AutopilotEngine().evaluate(
                {"active": False, "reason": "normal"},
                unified_mode="NORMAL",
                gov_mode="NORMAL",
            )
            self.assertEqual(status["state"], "running")
            self.assertTrue(status["allow"])
            blocked, reason = execution_gate(status)
            self.assertFalse(blocked)
            self.assertEqual(reason, "normal")

    def test_execution_path_paused_zeroes_orders(self):
        with mock.patch.dict(
            os.environ,
            {"AUTOPILOT_ENABLED": "1", "AUTOPILOT_PAUSED": "1"},
            clear=False,
        ):
            status = AutopilotEngine().evaluate()
            blocked, reason = execution_gate(status)
            self.assertTrue(blocked)
            self.assertEqual(reason, "autopilot_paused")

            size = 0.0 if blocked else 0.1
            orders = []
            if not blocked:
                r = Registry()
                r.register_account("A", MockAdapter("A"))
                orders = ExecutionOptimizer(r).run(
                    {("A", "EURUSD"): {"trend": {"signal": "BUY"}}},
                    {"A": 1.0},
                    size=size,
                )
            self.assertEqual(size, 0.0)
            self.assertEqual(orders, [])

    def test_execution_path_allows_when_running(self):
        with mock.patch.dict(
            os.environ,
            {"AUTOPILOT_ENABLED": "1", "AUTOPILOT_PAUSED": "0"},
            clear=False,
        ):
            status = AutopilotEngine().evaluate(unified_mode="NORMAL")
            blocked, _ = execution_gate(status)
            self.assertFalse(blocked)

            r = Registry()
            r.register_account("A", MockAdapter("A"))
            orders = ExecutionOptimizer(r).run(
                {("A", "EURUSD"): {"trend": {"signal": "BUY"}}},
                {"A": 1.0},
                size=0.1,
            )
            self.assertGreater(len(orders), 0)


if __name__ == "__main__":
    unittest.main()
