"""Account drawdown / SAFE_MODE risk-off gate for the live pipeline."""

from __future__ import annotations

import os
from typing import Any, Mapping

try:
    from infra.modes import SAFE_MODE
except ImportError:  # package import as prop_algo.* (pytest / non-Docker)
    from prop_algo.infra.modes import SAFE_MODE


def _env_flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


class RiskOffEngine:
    """Scale or block size when drawdown or SAFE_MODE is active.

    Mock equity wobble (±50) stays above the drawdown trip, so compose stays
    tradeable unless SAFE_MODE or a real drawdown is present.
    """

    DRAWDOWN_LIMIT = -100.0
    # Matches ExecutionOptimizer skip threshold (risk < 0.3).
    BLOCK_FACTOR = 0.2

    @classmethod
    def enabled(cls) -> bool:
        """``RISK_OFF_ENABLED=1`` turns the gate on (default on)."""
        return _env_flag("RISK_OFF_ENABLED", "1")

    def compute(self, account, df=None, *args, mode=None):
        if not self.enabled():
            return 1.0, {"reason": "disabled", "active": False, "factor": 1.0}

        if mode is not None and str(mode).upper() == SAFE_MODE:
            return 0.0, {
                "reason": "SAFE_MODE",
                "active": True,
                "factor": 0.0,
            }

        equity = float((account or {}).get("equity", 0.0))
        balance = float((account or {}).get("balance", 0.0))
        dd = equity - balance
        if dd < self.DRAWDOWN_LIMIT:
            return self.BLOCK_FACTOR, {
                "reason": "drawdown",
                "active": True,
                "factor": self.BLOCK_FACTOR,
                "drawdown": dd,
            }
        return 1.0, {
            "reason": "normal",
            "active": False,
            "factor": 1.0,
            "drawdown": dd,
        }

    def evaluate(
        self,
        accounts: Mapping[str, Mapping[str, Any]] | None,
        *,
        mode: str | None = None,
    ) -> dict[str, Any]:
        """Build a ``risk_stream`` / ``execution_stream`` risk_off payload."""
        accounts = accounts or {}
        if not self.enabled():
            return {
                "enabled": False,
                "active": False,
                "reason": "disabled",
                "factors": {name: 1.0 for name in accounts},
                "accounts": {},
            }

        factors: dict[str, float] = {}
        metas: dict[str, dict] = {}
        active = False
        reason = "normal"

        for name, info in accounts.items():
            factor, meta = self.compute(info, None, mode=mode)
            factors[name] = float(factor)
            metas[name] = meta
            if meta.get("active"):
                active = True
                # Prefer SAFE_MODE label when present.
                if meta.get("reason") == "SAFE_MODE":
                    reason = "SAFE_MODE"
                elif reason != "SAFE_MODE":
                    reason = str(meta.get("reason") or "risk_off")

        if mode is not None and str(mode).upper() == SAFE_MODE:
            active = True
            reason = "SAFE_MODE"
            factors = {name: 0.0 for name in factors}

        return {
            "enabled": True,
            "active": active,
            "reason": reason,
            "factors": factors,
            "accounts": metas,
        }


def execution_gate(
    risk_off: Mapping[str, Any] | None,
    *,
    unified_mode: str | None = None,
    gov_mode: str | None = None,
) -> tuple[bool, str]:
    """Return ``(blocked, reason)`` for the live execution path.

    When ``RISK_OFF_ENABLED`` is off, the gate is inert (allows), except an
    explicit governance ``HALT``.
    """
    gov = str(gov_mode or "").upper()
    if gov == "HALT":
        return True, "HALT"

    if not RiskOffEngine.enabled():
        return False, "disabled"

    uni = str(unified_mode or "").upper()
    if uni == SAFE_MODE:
        return True, "SAFE_MODE"
    if gov == SAFE_MODE:
        return True, "SAFE_MODE"

    if risk_off and risk_off.get("active"):
        return True, str(risk_off.get("reason") or "risk_off")

    return False, "normal"


def merge_risk_factors(
    budgets: Mapping[str, Any] | None,
    risk_off: Mapping[str, Any] | None,
) -> dict[str, float]:
    """Per-account factor = min(budget, risk_off factor); defaults to 1.0."""
    budgets = budgets or {}
    off_factors = (risk_off or {}).get("factors") or {}
    names = set(budgets) | set(off_factors)
    out: dict[str, float] = {}
    for name in names:
        try:
            b = float(budgets.get(name, 1.0))
        except (TypeError, ValueError):
            b = 1.0
        try:
            r = float(off_factors.get(name, 1.0))
        except (TypeError, ValueError):
            r = 1.0
        if not RiskOffEngine.enabled():
            out[name] = b
        else:
            out[name] = min(b, r)
    return out
