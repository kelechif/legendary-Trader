"""Unit tests for mission-control dashboard / alert payload merge helpers."""

from __future__ import annotations

import unittest

from prop_algo.mission_control.mission_alerts import generate_alerts
from prop_algo.mission_control.mission_controller import apply_mission_actions
from prop_algo.mission_control.mission_dashboard import (
    _marl_status,
    _simulation_status,
    build_dashboard,
)


def _base_snapshot(**overrides):
    snap = {
        "market": {"ACC1": {"equity": 10125.5, "balance": 10000}},
        "governance": {"rules": {"execution_mode": "NORMAL"}},
        "unified": {"mode": "STABLE", "stability": 0.9},
        "risk": {
            "anomalies": [],
            "liquidity": {"global_liquidity": 0.8},
        },
        "learning": {"meta_mode": "EXPLOIT"},
        "adapter": "mock",
        "autonomy": {"global_mode": "NORMAL"},
        "marl": {"actions": {"a1": 1, "a2": 0}},
        "simulation": {"status": "running", "steps": 12},
    }
    snap.update(overrides)
    return snap


class TestMissionDashboard(unittest.TestCase):
    def test_build_dashboard_merges_payload_fields(self):
        dash = build_dashboard(_base_snapshot())
        self.assertEqual(dash["equity"], 10125.5)
        self.assertEqual(dash["risk_mode"], "NORMAL")
        self.assertEqual(dash["unified_mode"], "STABLE")
        self.assertEqual(dash["anomalies"], [])
        self.assertEqual(dash["liquidity"], 0.8)
        self.assertEqual(dash["learning_meta_mode"], "EXPLOIT")
        self.assertEqual(dash["adapter"], "mock")
        self.assertEqual(dash["account_count"], 1)
        self.assertIn("ACC1", dash["accounts"])
        self.assertEqual(dash["autonomy_mode"], "NORMAL")
        self.assertEqual(dash["marl_status"], "agents=2")
        self.assertEqual(dash["simulation_status"], "running (12 steps)")

    def test_build_dashboard_multi_account_fields(self):
        snap = _base_snapshot(
            market={
                "ACC1": {"equity": 10100, "balance": 10000},
                "ACC2": {"equity": 9900, "balance": 9800},
            },
            multi_account={
                "enabled": True,
                "account_count": 2,
                "accounts": {
                    "ACC1": {"name": "ACC1", "equity": 10100, "balance": 10000},
                    "ACC2": {"name": "ACC2", "equity": 9900, "balance": 9800},
                },
            },
        )
        dash = build_dashboard(snap)
        self.assertEqual(dash["account_count"], 2)
        self.assertEqual(set(dash["accounts"]), {"ACC1", "ACC2"})

    def test_build_dashboard_falls_back_to_first_market_account(self):
        snap = _base_snapshot(
            market={"OTHER": {"equity": 42.0}},
            autonomy=None,
            marl=None,
            simulation=None,
        )
        dash = build_dashboard(snap)
        self.assertEqual(dash["equity"], 42.0)
        self.assertIsNone(dash["autonomy_mode"])
        self.assertIsNone(dash["marl_status"])
        self.assertIsNone(dash["simulation_status"])

    def test_marl_status_helpers(self):
        self.assertEqual(_marl_status({"status": "idle"}), "idle")
        self.assertEqual(_marl_status({}), "active")
        self.assertIsNone(_marl_status(None))

    def test_simulation_status_helpers(self):
        self.assertEqual(_simulation_status({"status": "done"}), "done")
        self.assertEqual(_simulation_status({}), "active")
        self.assertIsNone(_simulation_status("bad"))

    def test_alerts_and_actions_from_stressed_snapshot(self):
        snap = _base_snapshot(
            risk={
                "anomalies": list(range(6)),
                "liquidity": {"global_liquidity": 0.2},
            },
            unified={"mode": "SAFE", "stability": 0.1},
        )
        alerts = generate_alerts(snap)
        self.assertIn("Liquidity stress", alerts)
        self.assertIn("System instability", alerts)
        self.assertIn("Anomaly overload", alerts)

        actions = apply_mission_actions(alerts)
        self.assertIn("Switch execution to LIMIT_ONLY", actions)
        self.assertIn("Reduce position sizes", actions)
        self.assertIn("Throttle trading frequency", actions)

    def test_healthy_snapshot_no_alerts(self):
        self.assertEqual(generate_alerts(_base_snapshot()), [])
        self.assertEqual(apply_mission_actions([]), [])

    def test_autopilot_dashboard_and_alerts(self):
        running = _base_snapshot(
            execution={
                "route": "MARKET",
                "slippage": 0.0005,
                "volatility": 0.001,
                "size": 0.1,
                "autopilot": {
                    "enabled": True,
                    "paused": False,
                    "allow": True,
                    "state": "running",
                    "reason": "normal",
                },
            }
        )
        self.assertEqual(build_dashboard(running)["autopilot"], "running")
        self.assertEqual(generate_alerts(running), [])

        paused = _base_snapshot(
            execution={
                "route": "MARKET",
                "slippage": 0.0005,
                "volatility": 0.001,
                "size": 0.0,
                "blocked": True,
                "block_reason": "autopilot_paused",
                "autopilot": {
                    "enabled": True,
                    "paused": True,
                    "allow": False,
                    "state": "paused",
                    "reason": "paused",
                },
            }
        )
        self.assertEqual(build_dashboard(paused)["autopilot"], "paused (paused)")
        self.assertEqual(build_dashboard(paused)["risk_off"], "normal")
        self.assertIn("Autopilot paused: paused", generate_alerts(paused))

        off = _base_snapshot(
            execution={
                "route": "MARKET",
                "slippage": 0.0005,
                "volatility": 0.001,
                "size": 0.0,
                "blocked": True,
                "block_reason": "autopilot_off",
                "autopilot": {
                    "enabled": False,
                    "paused": False,
                    "allow": False,
                    "state": "off",
                    "reason": "disabled",
                },
            }
        )
        self.assertEqual(build_dashboard(off)["autopilot"], "off")
        self.assertIn("Autopilot off", generate_alerts(off))


if __name__ == "__main__":
    unittest.main()

