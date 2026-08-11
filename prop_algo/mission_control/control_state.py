"""Shared mission control plane (pause / resume / force SAFE).

Primary store is a Redis string key (visible to all compose services).
Falls back to a JSON file under ``state/`` when Redis is unreachable
(local unit tests, host-only runs).

Auth is intentionally omitted for local compose; do not expose Mission UI
to untrusted networks without a reverse-proxy auth layer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

REDIS_KEY = os.getenv("MISSION_CONTROL_REDIS_KEY", "mission:control")
FILE_PATH = Path(os.getenv("MISSION_CONTROL_FILE", "state/control.json"))

_DEFAULT: dict[str, Any] = {
    "autopilot_paused": False,
    "trading_halt": False,
    "force_safe": False,
}


def _defaults() -> dict[str, Any]:
    return dict(_DEFAULT)


def _normalize(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    out = _defaults()
    if not isinstance(raw, Mapping):
        return out
    for key in _DEFAULT:
        if key in raw:
            out[key] = bool(raw[key])
    return out


def _redis_client():
    """Return a Redis client or None when unavailable."""
    try:
        import redis
    except ImportError:
        return None
    host = os.getenv("REDIS_HOST", "redis")
    port = int(os.getenv("REDIS_PORT", "6379"))
    try:
        client = redis.Redis(
            host=host,
            port=port,
            socket_connect_timeout=float(os.getenv("MISSION_CONTROL_REDIS_TIMEOUT", "0.5")),
            socket_timeout=float(os.getenv("MISSION_CONTROL_REDIS_TIMEOUT", "0.5")),
        )
        client.ping()
        return client
    except Exception:
        return None


def _read_file(path: Path | None = None) -> dict[str, Any] | None:
    p = path or FILE_PATH
    try:
        with open(p, encoding="utf-8") as f:
            return _normalize(json.load(f))
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _write_file(state: Mapping[str, Any], path: Path | None = None) -> None:
    p = path or FILE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_normalize(state), f, indent=2)
        f.write("\n")
    tmp.replace(p)


def get_control_state(
    *,
    redis_client=None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Load control state (Redis preferred, then file, else defaults)."""
    client = redis_client if redis_client is not None else _redis_client()
    if client is not None:
        try:
            raw = client.get(REDIS_KEY)
            if raw:
                data = json.loads(raw)
                return _normalize(data)
        except Exception:
            pass

    from_file = _read_file(path)
    if from_file is not None:
        return from_file
    return _defaults()


def set_control_state(
    updates: Mapping[str, Any] | None = None,
    *,
    redis_client=None,
    path: Path | None = None,
    replace: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge ``updates`` into control state (or replace entirely) and persist."""
    if replace is not None:
        state = _normalize(replace)
    else:
        state = get_control_state(redis_client=redis_client, path=path)
        if updates:
            for key, value in updates.items():
                if key in _DEFAULT:
                    state[key] = bool(value)

    client = redis_client if redis_client is not None else _redis_client()
    if client is not None:
        try:
            client.set(REDIS_KEY, json.dumps(state))
        except Exception:
            pass

    try:
        _write_file(state, path)
    except Exception:
        pass

    return state


def pause_autopilot(**kwargs) -> dict[str, Any]:
    return set_control_state({"autopilot_paused": True}, **kwargs)


def resume_autopilot(**kwargs) -> dict[str, Any]:
    return set_control_state({"autopilot_paused": False}, **kwargs)


def set_trading_halt(active: bool, **kwargs) -> dict[str, Any]:
    return set_control_state({"trading_halt": bool(active)}, **kwargs)


def set_force_safe(active: bool, **kwargs) -> dict[str, Any]:
    return set_control_state({"force_safe": bool(active)}, **kwargs)


def control_blocks_autopilot(state: Mapping[str, Any] | None = None) -> tuple[bool, str]:
    """Return ``(blocked, reason)`` from control-plane flags only."""
    s = _normalize(state) if state is not None else get_control_state()
    if s.get("trading_halt"):
        return True, "trading_halt"
    if s.get("autopilot_paused"):
        return True, "paused"
    if s.get("force_safe"):
        return True, "SAFE_MODE"
    return False, "normal"


def mode_override_from_control(
    state: Mapping[str, Any] | None = None,
    *,
    redis_client=None,
    path: Path | None = None,
) -> tuple[str | None, str | None]:
    """Return ``(mode, reason)`` when operator control overrides stream mode.

    Precedence: ``trading_halt`` → ``HALT``, ``force_safe`` → ``SAFE_MODE``,
    otherwise ``(None, None)`` so callers keep the stream-derived mode.
    """
    if state is None:
        s = get_control_state(redis_client=redis_client, path=path)
    else:
        s = _normalize(state)
    if s.get("trading_halt"):
        return "HALT", "trading_halt"
    if s.get("force_safe"):
        return "SAFE_MODE", "force_safe"
    return None, None
