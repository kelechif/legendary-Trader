"""Unit tests for Mission Control shared control state + autopilot gate."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from prop_algo.mission_control.control_state import (
    control_blocks_autopilot,
    get_control_state,
    pause_autopilot,
    resume_autopilot,
    set_control_state,
    set_force_safe,
    set_trading_halt,
)
from prop_algo.trading.autopilot.autopilot_engine import (
    AutopilotEngine,
    execution_gate,
)


class TestControlState(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "control.json"
        # Force file-only path: no live Redis in unit tests.
        self._redis_patch = mock.patch(
            "prop_algo.mission_control.control_state._redis_client",
            return_value=None,
        )
        self._redis_patch.start()

    def tearDown(self):
        self._redis_patch.stop()
        self._tmpdir.cleanup()

    def test_defaults(self):
        state = get_control_state(path=self.path)
        self.assertFalse(state["autopilot_paused"])
        self.assertFalse(state["trading_halt"])
        self.assertFalse(state["force_safe"])

    def test_pause_resume_roundtrip(self):
        paused = pause_autopilot(path=self.path)
        self.assertTrue(paused["autopilot_paused"])
        loaded = get_control_state(path=self.path)
        self.assertTrue(loaded["autopilot_paused"])
        resumed = resume_autopilot(path=self.path)
        self.assertFalse(resumed["autopilot_paused"])
        self.assertFalse(get_control_state(path=self.path)["autopilot_paused"])

    def test_force_safe_and_halt(self):
        set_force_safe(True, path=self.path)
        self.assertTrue(get_control_state(path=self.path)["force_safe"])
        set_trading_halt(True, path=self.path)
        state = get_control_state(path=self.path)
        self.assertTrue(state["trading_halt"])
        self.assertTrue(state["force_safe"])
        blocked, reason = control_blocks_autopilot(state)
        self.assertTrue(blocked)
        self.assertEqual(reason, "trading_halt")

    def test_control_blocks_reasons(self):
        blocked, reason = control_blocks_autopilot(
            {"autopilot_paused": True, "trading_halt": False, "force_safe": False}
        )
        self.assertTrue(blocked)
        self.assertEqual(reason, "paused")

        blocked, reason = control_blocks_autopilot(
            {"autopilot_paused": False, "trading_halt": False, "force_safe": True}
        )
        self.assertTrue(blocked)
        self.assertEqual(reason, "SAFE_MODE")

        blocked, reason = control_blocks_autopilot({})
        self.assertFalse(blocked)
        self.assertEqual(reason, "normal")

    def test_set_control_state_replace(self):
        set_control_state(
            replace={
                "autopilot_paused": True,
                "trading_halt": True,
                "force_safe": False,
                "ignored": 1,
            },
            path=self.path,
        )
        state = get_control_state(path=self.path)
        self.assertTrue(state["autopilot_paused"])
        self.assertTrue(state["trading_halt"])
        self.assertFalse(state["force_safe"])
        self.assertNotIn("ignored", state)


class TestAutopilotControlGate(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "control.json"
        self._redis_patch = mock.patch(
            "prop_algo.mission_control.control_state._redis_client",
            return_value=None,
        )
        self._redis_patch.start()
        # Point AutopilotEngine at our temp file via get_control_state wrapper.
        self._get_patch = mock.patch(
            "prop_algo.trading.autopilot.autopilot_engine.get_control_state",
            side_effect=lambda **kw: get_control_state(path=self.path, **kw),
        )
        self._get_patch.start()

    def tearDown(self):
        self._get_patch.stop()
        self._redis_patch.stop()
        self._tmpdir.cleanup()

    def test_control_pause_blocks_evaluate(self):
        with mock.patch.dict(
            os.environ,
            {"AUTOPILOT_ENABLED": "1", "AUTOPILOT_PAUSED": "0"},
            clear=False,
        ):
            pause_autopilot(path=self.path)
            status = AutopilotEngine().evaluate()
            self.assertTrue(status["paused"])
            self.assertFalse(status["allow"])
            self.assertEqual(status["reason"], "paused")
            blocked, reason = execution_gate(status)
            self.assertTrue(blocked)
            self.assertEqual(reason, "autopilot_paused")

    def test_control_resume_allows(self):
        with mock.patch.dict(
            os.environ,
            {"AUTOPILOT_ENABLED": "1", "AUTOPILOT_PAUSED": "0"},
            clear=False,
        ):
            pause_autopilot(path=self.path)
            resume_autopilot(path=self.path)
            status = AutopilotEngine().evaluate(unified_mode="NORMAL")
            self.assertTrue(status["allow"])
            self.assertEqual(status["state"], "running")

    def test_force_safe_blocks_as_safe_mode(self):
        with mock.patch.dict(
            os.environ,
            {"AUTOPILOT_ENABLED": "1", "AUTOPILOT_PAUSED": "0"},
            clear=False,
        ):
            set_force_safe(True, path=self.path)
            status = AutopilotEngine().evaluate()
            self.assertTrue(status["paused"])
            self.assertEqual(status["reason"], "SAFE_MODE")
            blocked, reason = execution_gate(status)
            self.assertTrue(blocked)
            self.assertEqual(reason, "SAFE_MODE")

    def test_trading_halt_blocks(self):
        with mock.patch.dict(
            os.environ,
            {"AUTOPILOT_ENABLED": "1", "AUTOPILOT_PAUSED": "0"},
            clear=False,
        ):
            set_trading_halt(True, path=self.path)
            status = AutopilotEngine().evaluate()
            self.assertEqual(status["reason"], "trading_halt")
            blocked, reason = execution_gate(status)
            self.assertTrue(blocked)
            self.assertEqual(reason, "trading_halt")

    def test_env_pause_still_wins(self):
        with mock.patch.dict(
            os.environ,
            {"AUTOPILOT_ENABLED": "1", "AUTOPILOT_PAUSED": "1"},
            clear=False,
        ):
            resume_autopilot(path=self.path)
            status = AutopilotEngine().evaluate()
            self.assertEqual(status["reason"], "paused")


if __name__ == "__main__":
    unittest.main()
