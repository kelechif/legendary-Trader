"""Unit tests for MultiAccountManager registration / routing."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from prop_algo.core.adapters.mock_adapter import MockAdapter
from prop_algo.core.registry.registry import Registry
from prop_algo.trading.execution.execution_optimizer import ExecutionOptimizer
from prop_algo.trading.multi_account.manager import MultiAccountManager


def _registry_two():
    r = Registry()
    r.register_account("ACC1", MockAdapter("ACC1"))
    r.register_account("ACC2", MockAdapter("ACC2"))
    return r


class TestMultiAccountManager(unittest.TestCase):
    def test_enabled_defaults_on(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MULTI_ACCOUNT_ENABLED", None)
            self.assertTrue(MultiAccountManager.enabled())

    def test_enabled_off(self):
        with mock.patch.dict(os.environ, {"MULTI_ACCOUNT_ENABLED": "0"}):
            self.assertFalse(MultiAccountManager.enabled())

    def test_tracks_registry_accounts(self):
        mgr = MultiAccountManager(_registry_two())
        self.assertEqual(mgr.account_count(), 2)
        self.assertEqual(mgr.account_names(), ["ACC1", "ACC2"])

    def test_snapshot_equity_balance(self):
        mgr = MultiAccountManager(_registry_two())
        snap = mgr.snapshot()
        self.assertEqual(set(snap), {"ACC1", "ACC2"})
        for name, row in snap.items():
            self.assertEqual(row["name"], name)
            self.assertIn("equity", row)
            self.assertIn("balance", row)
            self.assertIsNotNone(row["balance"])

    def test_place_order_attributes_account(self):
        mgr = MultiAccountManager(_registry_two())
        res = mgr.place_order("ACC2", "EURUSD", 0.2, None, None, route="LIMIT")
        self.assertEqual(res["account"], "ACC2")
        self.assertEqual(res["symbol"], "EURUSD")
        self.assertEqual(res["status"], "FILLED")
        self.assertEqual(res["route"], "LIMIT")

    def test_place_order_unknown_account(self):
        mgr = MultiAccountManager(_registry_two())
        with self.assertRaises(KeyError):
            mgr.place_order("MISSING", "EURUSD", 0.1)

    def test_broadcast_active_accounts(self):
        with mock.patch.dict(os.environ, {"MULTI_ACCOUNT_ENABLED": "1"}):
            mgr = MultiAccountManager(_registry_two())
            results = mgr.broadcast(
                {"symbol": "EURUSD", "size": 0.1, "sl": None, "tp": None}
            )
        self.assertEqual(len(results), 2)
        self.assertEqual({r["account"] for r in results}, {"ACC1", "ACC2"})
        self.assertTrue(all(r["status"] == "FILLED" for r in results))

    def test_broadcast_disabled_routes_first_only(self):
        with mock.patch.dict(os.environ, {"MULTI_ACCOUNT_ENABLED": "0"}):
            mgr = MultiAccountManager(_registry_two())
            self.assertEqual(mgr.active_accounts(), ["ACC1"])
            results = mgr.broadcast(
                {"symbol": "EURUSD", "size": 0.1, "sl": None, "tp": None}
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["account"], "ACC1")

    def test_route_order_explicit_account(self):
        mgr = MultiAccountManager(_registry_two())
        results = mgr.route_order(
            {"symbol": "GBPUSD", "size": 0.5}, account="ACC2"
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["account"], "ACC2")
        self.assertEqual(results[0]["symbol"], "GBPUSD")

    def test_summary(self):
        with mock.patch.dict(os.environ, {"MULTI_ACCOUNT_ENABLED": "1"}):
            mgr = MultiAccountManager(_registry_two())
            summary = mgr.summary()
        self.assertTrue(summary["enabled"])
        self.assertEqual(summary["account_count"], 2)
        self.assertEqual(summary["active_accounts"], ["ACC1", "ACC2"])
        self.assertEqual(set(summary["accounts"]), {"ACC1", "ACC2"})

    def test_execution_optimizer_attributes_orders(self):
        with mock.patch.dict(os.environ, {"MULTI_ACCOUNT_ENABLED": "1"}):
            r = _registry_two()
            mgr = MultiAccountManager(r)
            opt = ExecutionOptimizer(r, multi_account=mgr)
            signals = {
                ("ACC1", "EURUSD"): {"trend": {"signal": "BUY"}},
                ("ACC2", "EURUSD"): {"trend": {"signal": "BUY"}},
            }
            orders = opt.run(signals, {"ACC1": 1.0, "ACC2": 1.0}, route="MARKET")
        self.assertEqual(len(orders), 2)
        self.assertEqual({o["account"] for o in orders}, {"ACC1", "ACC2"})
        self.assertTrue(all(o.get("route") == "MARKET" for o in orders))

    def test_execution_optimizer_disabled_skips_secondary(self):
        with mock.patch.dict(os.environ, {"MULTI_ACCOUNT_ENABLED": "0"}):
            r = _registry_two()
            opt = ExecutionOptimizer(r)
            signals = {
                ("ACC1", "EURUSD"): {"trend": {"signal": "BUY"}},
                ("ACC2", "EURUSD"): {"trend": {"signal": "BUY"}},
            }
            orders = opt.run(signals, {"ACC1": 1.0, "ACC2": 1.0})
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["account"], "ACC1")


if __name__ == "__main__":
    unittest.main()
