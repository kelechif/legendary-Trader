"""Autopilot gate for strategy→execution in the live pipeline."""

from __future__ import annotations

import os
from typing import Any, Mapping

try:
    from infra.modes import SAFE_MODE
except ImportError:  # package import as prop_algo.* (pytest / non-Docker)
    from prop_algo.infra.modes import SAFE_MODE

try:
    from mission_control.control_state import (
        control_blocks_autopilot,
        get_control_state,
    )
except ImportError:
    from prop_algo.mission_control.control_state import (
        control_blocks_autopilot,
        get_control_state,
    )


def _env_flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


class AutopilotEngine:
    """Enable / pause autonomous trading from mission / risk / gov state.

    ``AUTOPILOT_ENABLED=1`` (default) turns autopilot on. When off or paused,
    new orders are blocked (size=0) with a clear reason on streams.

    Pause triggers: ``AUTOPILOT_PAUSED=1``, shared Mission Control state
    (``autopilot_paused`` / ``trading_halt`` / ``force_safe``), governance
    ``HALT``, ``SAFE_MODE`` (unified / gov / mission), or active risk-off.
    """

    @classmethod
    def enabled(cls) -> bool:
        """``AUTOPILOT_ENABLED=1`` turns autopilot on (default on)."""
        return _env_flag("AUTOPILOT_ENABLED", "1")

    @classmethod
    def env_paused(cls) -> bool:
        """``AUTOPILOT_PAUSED=1`` forces a pause while enabled."""
        return _env_flag("AUTOPILOT_PAUSED", "0")

    @classmethod
    def control_state(cls) -> dict[str, Any]:
        """Shared Mission Control plane (Redis / file); safe defaults on error."""
        try:
            return get_control_state()
        except Exception:
            return {
                "autopilot_paused": False,
                "trading_halt": False,
                "force_safe": False,
            }

    @classmethod
    def control_paused(cls) -> bool:
        """True when Mission Control pause / halt / force-SAFE is active."""
        blocked, _ = control_blocks_autopilot(cls.control_state())
        return blocked

    def should_trade(
        self,
        risk_off: Mapping[str, Any] | None = None,
        *args,
        unified_mode: str | None = None,
        gov_mode: str | None = None,
        mission: Mapping[str, Any] | None = None,
        **kwargs,
    ) -> bool:
        """Return True when new orders may be placed.

        Extra positional/keyword args are accepted for forward compatibility with
        the monolith call site (``if autopilot.should_trade():``).
        """
        del args, kwargs
        return bool(
            self.evaluate(
                risk_off,
                unified_mode=unified_mode,
                gov_mode=gov_mode,
                mission=mission,
            )["allow"]
        )

    def evaluate(
        self,
        risk_off: Mapping[str, Any] | None = None,
        *,
        unified_mode: str | None = None,
        gov_mode: str | None = None,
        mission: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build an ``execution_stream`` / Mission UI autopilot payload."""
        if not self.enabled():
            return {
                "enabled": False,
                "paused": False,
                "allow": False,
                "state": "off",
                "reason": "disabled",
            }

        mission_mode = None
        if isinstance(mission, Mapping):
            mission_mode = mission.get("global_mode") or mission.get("mode")

        gov = str(gov_mode or "").upper()
        uni = str(unified_mode or "").upper()
        miss = str(mission_mode or "").upper()

        if self.env_paused():
            return self._paused("paused")

        ctrl_blocked, ctrl_reason = control_blocks_autopilot(self.control_state())
        if ctrl_blocked:
            return self._paused(ctrl_reason)

        if gov == "HALT":
            return self._paused("HALT")
        if SAFE_MODE in (uni, gov, miss):
            return self._paused("SAFE_MODE")
        if risk_off and risk_off.get("active"):
            return self._paused(str(risk_off.get("reason") or "risk_off"))

        return {
            "enabled": True,
            "paused": False,
            "allow": True,
            "state": "running",
            "reason": "normal",
        }

    @staticmethod
    def _paused(reason: str) -> dict[str, Any]:
        return {
            "enabled": True,
            "paused": True,
            "allow": False,
            "state": "paused",
            "reason": reason,
        }


def execution_gate(
    autopilot: Mapping[str, Any] | None = None,
    *,
    risk_off: Mapping[str, Any] | None = None,
    unified_mode: str | None = None,
    gov_mode: str | None = None,
    mission: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    """Return ``(blocked, reason)`` for the live execution path.

    Prefer an existing ``autopilot`` status payload; otherwise evaluate from
    mission / risk / gov inputs. Blocked when autopilot is off or paused.
    """
    status = (
        dict(autopilot)
        if isinstance(autopilot, Mapping) and "allow" in autopilot
        else AutopilotEngine().evaluate(
            risk_off,
            unified_mode=unified_mode,
            gov_mode=gov_mode,
            mission=mission,
        )
    )
    if status.get("allow"):
        return False, str(status.get("reason") or "normal")

    reason = str(status.get("reason") or "autopilot")
    if status.get("state") == "off" or reason == "disabled":
        return True, "autopilot_off"
    if reason == "paused":
        return True, "autopilot_paused"
    if reason == "trading_halt":
        return True, "trading_halt"
    return True, reason
