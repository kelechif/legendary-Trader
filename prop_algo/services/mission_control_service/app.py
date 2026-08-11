"""mission-control-service: aggregate Redis streams into mission_stream."""

from __future__ import annotations

import time
from typing import Any

from core.adapters.factory import register_broker_accounts
from core.logging.logger import get_logger
from core.registry.registry import Registry
from infra.stream import Stream
from mission_control.mission_engine import MissionControlEngine

log = get_logger("mission-control-service")
SERVICE = "mission-control-service"

_DEFAULT_LEARNING = {
    "best_params": {"threshold": 0.005, "lookback": 50, "fitness": 0.0},
    "meta_mode": "NORMAL",
}
_DEFAULT_EXECUTION = {
    "route": "MARKET",
    "slippage": 0.0005,
    "volatility": 0.001,
    "size": 0.1,
}


def _normalize_learning(learning: dict | None) -> dict:
    base = dict(_DEFAULT_LEARNING)
    if not learning:
        return base
    best = dict(base["best_params"])
    raw_best = learning.get("best_params") or {}
    if isinstance(raw_best, dict):
        best.update(raw_best)
    if "threshold" not in best:
        best["threshold"] = 0.005
    out = dict(learning)
    out["best_params"] = best
    out.setdefault("meta_mode", base["meta_mode"])
    return out


def _normalize_execution(execution: Any) -> dict:
    if isinstance(execution, dict) and "route" in execution:
        out = {
            "route": execution.get("route", "MARKET"),
            "slippage": float(execution.get("slippage", 0.0005)),
            "volatility": float(execution.get("volatility", 0.001)),
            "size": float(execution.get("size", 0.1)),
        }
        if "backend" in execution:
            out["backend"] = execution.get("backend")
        if "neural_enabled" in execution:
            out["neural_enabled"] = bool(execution.get("neural_enabled"))
        return out
    return dict(_DEFAULT_EXECUTION)


def _market_probe(registry: Registry) -> dict:
    return {
        name: profile["adapter"].get_account_info()
        for name, profile in registry.accounts.items()
    }


def run_loop(bus: Stream | None = None, poll_block_ms: int = 200) -> None:
    bus = bus or Stream()
    engine = MissionControlEngine()
    registry = Registry()
    adapter_kind = register_broker_accounts(registry)
    log.info("%s broker adapter=%s", SERVICE, adapter_kind)

    last: dict[str, Any] = {
        "risk": None,
        "governance": None,
        "unified": None,
        "learning": None,
        "execution": None,
        "autonomy": None,
        "marl": None,
        "simulation": None,
    }
    streams = (
        ("risk", "risk_stream"),
        ("governance", "governance_stream"),
        ("unified", "unified_core_stream"),
        ("learning", "learning_stream"),
        ("execution", "execution_stream"),
        # Optional / torch-profile publishers — folded into mission when present.
        ("autonomy", "autonomy_stream"),
        ("marl", "marl_stream"),
        ("simulation", "simulation_stream"),
    )

    log.info("%s aggregating streams -> mission_stream", SERVICE)

    while True:
        updated = False
        for i, (key, stream_name) in enumerate(streams):
            # Block only on the first stream; drain the rest quickly.
            block = poll_block_ms if i == 0 else 1
            msg = bus.consume(
                stream_name, "mission_group", "mission_consumer", block=block
            )
            if msg is not None:
                last[key] = msg
                updated = True

        if not (last["risk"] and last["governance"] and last["unified"]):
            if not updated:
                time.sleep(0.25)
            continue

        if not updated:
            time.sleep(0.05)
            continue

        probes = {
            "market": _market_probe(registry),
            "risk": last["risk"],
            "governance": last["governance"],
            "unified": last["unified"],
            "learning": _normalize_learning(last["learning"]),
            "execution": _normalize_execution(last["execution"]),
            "adapter": adapter_kind,
        }
        if last["autonomy"] is not None:
            probes["autonomy"] = last["autonomy"]
        if last["marl"] is not None:
            probes["marl"] = last["marl"]
        if last["simulation"] is not None:
            probes["simulation"] = last["simulation"]
        result = engine.run(probes)
        snapshot = {
            **probes,
            "alerts": result["alerts"],
            "dashboard": result["dashboard"],
            "actions": result["actions"],
            "global_mode": result["global_mode"],
        }
        bus.publish("mission_stream", snapshot)


def run():
    """Backward-compatible entry used by older stubs."""
    run_loop()
