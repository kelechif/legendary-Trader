"""Unit tests for RiskOffEngine and the live execution gate."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from prop_algo.core.adapters.mock_adapter import MockAdapter
from prop_algo.core.registry.registry import Registry
from prop_algo.trading.execution.execution_optimizer import ExecutionOptimizer
from prop_algo.trading.risk_off.risk_off_engine import (
    RiskOffEngine,
    execution_gate,
    merge_risk_factors,
)


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
        self.assertTrue(meta["active"])

    def test_safe_mode_zeros_factor(self):
        engine = RiskOffEngine()
        factor, meta = engine.compute(
            {"equity": 10000, "balance": 10000}, None, mode="SAFE_MODE"
        )
        self.assertEqual(factor, 0.0)
        self.assertEqual(meta["reason"], "SAFE_MODE")
        self.assertTrue(meta["active"])

    def test_evaluate_marks_active_on_drawdown(self):
        engine = RiskOffEngine()
        payload = engine.evaluate(
            {
                "ACC1": {"equity": 9800, "balance": 10000},
                "ACC2": {"equity": 10000, "balance": 10000},
            }
        )
        self.assertTrue(payload["enabled"])
        self.assertTrue(payload["active"])
        self.assertEqual(payload["reason"], "drawdown")
        self.assertEqual(payload["factors"]["ACC1"], 0.2)
        self.assertEqual(payload["factors"]["ACC2"], 1.0)

    def test_enabled_env_flag(self):
        with mock.patch.dict(os.environ, {"RISK_OFF_ENABLED": "0"}, clear=False):
            self.assertFalse(RiskOffEngine.enabled())
            factor, meta = RiskOffEngine().compute(
                {"equity": 9000, "balance": 10000}, None
            )
            self.assertEqual(factor, 1.0)
            self.assertEqual(meta["reason"], "disabled")
        with mock.patch.dict(os.environ, {"RISK_OFF_ENABLED": "1"}, clear=False):
            self.assertTrue(RiskOffEngine.enabled())

    def test_execution_gate_blocks_safe_mode(self):
        with mock.patch.dict(os.environ, {"RISK_OFF_ENABLED": "1"}, clear=False):
            blocked, reason = execution_gate({}, unified_mode="SAFE_MODE")
            self.assertTrue(blocked)
            self.assertEqual(reason, "SAFE_MODE")

    def test_execution_gate_blocks_risk_off_active(self):
        with mock.patch.dict(os.environ, {"RISK_OFF_ENABLED": "1"}, clear=False):
            blocked, reason = execution_gate(
                {"active": True, "reason": "drawdown"}
            )
            self.assertTrue(blocked)
            self.assertEqual(reason, "drawdown")

    def test_execution_gate_allows_normal(self):
        with mock.patch.dict(os.environ, {"RISK_OFF_ENABLED": "1"}, clear=False):
            blocked, reason = execution_gate(
                {"active": False, "reason": "normal"},
                unified_mode="NORMAL",
            )
            self.assertFalse(blocked)
            self.assertEqual(reason, "normal")

    def test_execution_gate_disabled_allows_even_if_active(self):
        with mock.patch.dict(os.environ, {"RISK_OFF_ENABLED": "0"}, clear=False):
            blocked, reason = execution_gate(
                {"active": True, "reason": "drawdown"},
                unified_mode="SAFE_MODE",
            )
            self.assertFalse(blocked)
            self.assertEqual(reason, "disabled")

    def test_merge_risk_factors_takes_min(self):
        with mock.patch.dict(os.environ, {"RISK_OFF_ENABLED": "1"}, clear=False):
            merged = merge_risk_factors(
                {"ACC1": 0.5, "ACC2": 1.0},
                {"factors": {"ACC1": 0.2, "ACC2": 1.0}},
            )
            self.assertEqual(merged["ACC1"], 0.2)
            self.assertEqual(merged["ACC2"], 1.0)

    def test_execution_path_blocked_zeroes_orders(self):
        """Live-path shape: gate blocks → size 0 and optimizer not run / empty."""
        with mock.patch.dict(os.environ, {"RISK_OFF_ENABLED": "1"}, clear=False):
            risk_off = RiskOffEngine().evaluate(
                {"A": {"equity": 9800, "balance": 10000}}
            )
            blocked, reason = execution_gate(risk_off)
            self.assertTrue(blocked)
            self.assertEqual(reason, "drawdown")

            size = 0.0 if blocked else 0.1
            orders = []
            if not blocked:
                r = Registry()
                r.register_account("A", MockAdapter("A"))
                orders = ExecutionOptimizer(r).run(
                    {("A", "EURUSD"): {"trend": {"signal": "BUY"}}},
                    risk_off["factors"],
                    size=size,
                )
            self.assertEqual(size, 0.0)
            self.assertEqual(orders, [])

    def test_execution_path_allows_normal_orders(self):
        with mock.patch.dict(os.environ, {"RISK_OFF_ENABLED": "1"}, clear=False):
            risk_off = RiskOffEngine().evaluate(
                {"A": {"equity": 10000, "balance": 10000}}
            )
            blocked, _ = execution_gate(risk_off, unified_mode="NORMAL")
            self.assertFalse(blocked)

            r = Registry()
            r.register_account("A", MockAdapter("A"))
            orders = ExecutionOptimizer(r).run(
                {("A", "EURUSD"): {"trend": {"signal": "BUY"}}},
                merge_risk_factors({"A": 1.0}, risk_off),
                size=0.1,
            )
            self.assertGreater(len(orders), 0)


if __name__ == "__main__":
    unittest.main()
