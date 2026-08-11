#!/usr/bin/env python3
"""Host-side smoke test against a local light (or light+torch) stack.

Checks:
  - Redis PING
  - Mission UI HTTP 200
  - Mission UI ``GET /api/control`` returns control-plane JSON
  - WebSocket delivers a mission_stream payload with an ``adapter`` field
  - Optional: Redis stream lengths for core + optional torch streams

Usage (repo root or this directory; stack already up on localhost):

  python prop_algo/deploy/smoke_test.py
  python prop_algo/deploy/smoke_test.py --timeout 60 --check-streams

Env overrides:
  REDIS_HOST (default 127.0.0.1), REDIS_PORT (6379),
  MISSION_UI_URL (default http://127.0.0.1:8080)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

CORE_STREAMS = (
    "market_data_stream",
    "risk_stream",
    "governance_stream",
    "unified_core_stream",
    "execution_stream",
    "learning_stream",
    "mission_stream",
    "autonomy_stream",
)
OPTIONAL_STREAMS = (
    "marl_stream",
    "simulation_stream",
)


def _ok(msg: str) -> None:
    print(f"OK  {msg}")


def _fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def _redis_client(host: str, port: int):
    import redis

    return redis.Redis(host=host, port=port, socket_connect_timeout=3)


def check_redis(host: str, port: int) -> bool:
    try:
        r = _redis_client(host, port)
        if r.ping():
            _ok(f"redis ping {host}:{port}")
            return True
        _fail("redis ping returned falsy")
        return False
    except ImportError:
        pass
    except Exception as exc:
        _fail(f"redis ping {host}:{port}: {exc}")
        return False

    # Fallback: docker compose redis container (no host redis package needed).
    import subprocess

    try:
        out = subprocess.check_output(
            ["docker", "exec", "prop_algo-redis-1", "redis-cli", "ping"],
            stderr=subprocess.STDOUT,
            timeout=5,
            text=True,
        )
        if "PONG" in out.upper():
            _ok("redis ping via docker exec prop_algo-redis-1")
            return True
        _fail(f"redis-cli unexpected: {out.strip()!r}")
        return False
    except Exception as exc:
        _fail(
            f"redis unreachable (pip install redis, or ensure prop_algo-redis-1 is up): {exc}"
        )
        return False


def check_http(url: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                code = resp.getcode()
                if code == 200:
                    _ok(f"Mission UI HTTP {code} {url}")
                    return True
                last_err = RuntimeError(f"HTTP {code}")
        except Exception as exc:
            last_err = exc
        time.sleep(1)
    _fail(f"Mission UI HTTP {url}: {last_err}")
    return False


def check_control_api(ui_url: str, timeout: float) -> bool:
    """GET /api/control — operator control plane must respond with flags."""
    url = ui_url.rstrip("/") + "/api/control"
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                code = resp.getcode()
                body = resp.read().decode("utf-8", errors="replace")
                if code != 200:
                    last_err = RuntimeError(f"HTTP {code}")
                    time.sleep(1)
                    continue
                data = json.loads(body)
                for key in ("autopilot_paused", "trading_halt", "force_safe"):
                    if key not in data:
                        last_err = RuntimeError(f"missing key {key}")
                        break
                else:
                    _ok(
                        f"control API {url} "
                        f"paused={data['autopilot_paused']} "
                        f"halt={data['trading_halt']} "
                        f"safe={data['force_safe']}"
                    )
                    return True
        except Exception as exc:
            last_err = exc
        time.sleep(1)
    _fail(f"control API {url}: {last_err}")
    return False


def check_ws(ws_url: str, timeout: float) -> bool:
    try:
        from websocket import create_connection
    except ImportError:
        _fail("websocket-client not installed (pip install websocket-client)")
        return False

    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            ws = create_connection(ws_url, timeout=min(10, timeout))
            try:
                remaining = max(1.0, deadline - time.time())
                ws.settimeout(remaining)
                raw = ws.recv()
            finally:
                ws.close()
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError(f"expected object, got {type(payload).__name__}")
            if "adapter" not in payload:
                raise ValueError("mission payload missing 'adapter' field")
            mode = payload.get("global_mode") or (payload.get("dashboard") or {}).get(
                "risk_mode"
            )
            _ok(
                f"WebSocket mission payload adapter={payload.get('adapter')!r} "
                f"mode={mode!r}"
            )
            extras = [
                k
                for k in ("autonomy", "marl", "simulation")
                if payload.get(k) is not None
            ]
            if extras:
                _ok(f"optional mission fields present: {', '.join(extras)}")
            return True
        except Exception as exc:
            last_err = exc
            time.sleep(1)
    _fail(f"WebSocket {ws_url}: {last_err}")
    return False


def _stream_len(name: str, host: str, port: int) -> int:
    try:
        return int(_redis_client(host, port).xlen(name))
    except ImportError:
        import subprocess

        out = subprocess.check_output(
            ["docker", "exec", "prop_algo-redis-1", "redis-cli", "XLEN", name],
            stderr=subprocess.STDOUT,
            timeout=5,
            text=True,
        )
        return int(out.strip())


def check_streams(host: str, port: int, include_optional: bool) -> bool:
    names = list(CORE_STREAMS)
    if include_optional:
        names.extend(OPTIONAL_STREAMS)
    ok = True
    for name in names:
        try:
            length = _stream_len(name, host, port)
            label = "OK " if length > 0 else "WARN"
            print(f"{label} stream {name} length={length}")
            if name == "mission_stream" and length == 0:
                ok = False
                _fail("mission_stream is empty")
        except Exception as exc:
            print(f"WARN stream {name}: {exc}")
            if name == "mission_stream":
                ok = False
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="prop_algo light-stack smoke test")
    parser.add_argument(
        "--redis-host",
        default=os.getenv("REDIS_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--redis-port",
        type=int,
        default=int(os.getenv("REDIS_PORT", "6379")),
    )
    parser.add_argument(
        "--ui-url",
        default=os.getenv("MISSION_UI_URL", "http://127.0.0.1:8080"),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="seconds to wait for UI / first WS mission payload",
    )
    parser.add_argument(
        "--check-streams",
        action="store_true",
        help="print Redis stream lengths (requires mission_stream > 0)",
    )
    parser.add_argument(
        "--torch-streams",
        action="store_true",
        help="also report marl_stream / simulation_stream lengths",
    )
    args = parser.parse_args(argv)

    ui = args.ui_url.rstrip("/")
    if ui.startswith("https://"):
        ws_url = "wss://" + ui[len("https://") :] + "/ws"
    else:
        ws_url = "ws://" + ui[len("http://") :] + "/ws"

    results = [
        check_redis(args.redis_host, args.redis_port),
        check_http(ui + "/", args.timeout),
        check_control_api(ui, args.timeout),
        check_ws(ws_url, args.timeout),
    ]
    if args.check_streams or args.torch_streams:
        results.append(
            check_streams(
                args.redis_host,
                args.redis_port,
                include_optional=args.torch_streams,
            )
        )

    if all(results):
        print("SMOKE PASS")
        return 0
    print("SMOKE FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
