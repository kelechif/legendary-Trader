#!/usr/bin/env python3
"""DEMO-only continuous host run: StrategyEngine signals -> tiny MT5 market orders.

Windows host MetaTrader 5 only (not Docker/mock). Aborts unless the account is
DEMO (trade_mode) and the server name looks like a demo server (e.g. MetaQuotes-Demo).
Never logs passwords. Lot size is capped at 0.01.

Usage (from repo root):

  py -3 prop_algo/deploy/demo_signal_week.py --duration-days 7
  py -3 prop_algo/deploy/demo_signal_week.py --duration-seconds 120 --cycle-seconds 30

Stop:
  kill the PID in prop_algo/deploy/logs/demo_signal_week.pid  (or Ctrl+C)
  Log: prop_algo/deploy/logs/demo_signal_week.log

Loads prop_algo/.env if present (MT5_LOGIN / MT5_PASSWORD / MT5_SERVER).
REDIS is not required.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow `python prop_algo/deploy/demo_signal_week.py` from repo root.
_PROP_ALGO = Path(__file__).resolve().parents[1]
_REPO_ROOT = _PROP_ALGO.parent
_DEPLOY = Path(__file__).resolve().parent
_LOG_DIR = _DEPLOY / "logs"
_LOG_FILE = _LOG_DIR / "demo_signal_week.log"
_PID_FILE = _LOG_DIR / "demo_signal_week.pid"

for _p in (_REPO_ROOT, _PROP_ALGO):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)

LOT_CAP = 0.01
DEFAULT_LOT = 0.01
DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD")
TRADEABLE = frozenset({"BUY", "SELL"})
SKIP_SIGNALS = frozenset({"HOLD", "NONE", ""})
FLAT_SIGNALS = frozenset({"FLAT"})
_STOP = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _safe_env_summary() -> dict:
    return {
        "BROKER_ADAPTER": os.getenv("BROKER_ADAPTER", ""),
        "MT5_LOGIN": os.getenv("MT5_LOGIN", ""),
        "MT5_SERVER": os.getenv("MT5_SERVER", ""),
        "MT5_PASSWORD_SET": bool((os.getenv("MT5_PASSWORD") or "").strip()),
        "MT5_PATH_SET": bool((os.getenv("MT5_PATH") or "").strip()),
        "MT5_SYMBOLS": os.getenv("MT5_SYMBOLS", ""),
    }


def _symbols_from_env() -> list[str]:
    raw = (os.getenv("MT5_SYMBOLS") or "").strip()
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip()]
    return list(DEFAULT_SYMBOLS)


def _primary_signal(acc_signals: dict, strategy: str) -> str:
    if strategy == "all":
        votes = [v.get("signal", "HOLD") for v in acc_signals.values()]
        buys = sum(1 for s in votes if s == "BUY")
        sells = sum(1 for s in votes if s == "SELL")
        if buys > sells and buys > 0:
            return "BUY"
        if sells > buys and sells > 0:
            return "SELL"
        return "HOLD"
    packed = acc_signals.get(strategy) or {}
    return str(packed.get("signal", "HOLD")).upper()


def _setup_logging() -> logging.Logger:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("demo_signal_week")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def _write_pid() -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def _clear_pid() -> None:
    try:
        if _PID_FILE.is_file():
            _PID_FILE.unlink()
    except OSError:
        pass


def _request_stop(signum, _frame) -> None:
    global _STOP
    _STOP = True
    # Avoid logging from signal handler on Windows; flag is enough.


def _assert_demo_gate(acct: dict, log: logging.Logger) -> None:
    server = str(acct.get("server") or "")
    is_demo = bool(acct.get("is_demo"))
    trade_mode = acct.get("trade_mode")
    server_ok = "demo" in server.lower()
    if not is_demo or not server_ok:
        raise RuntimeError(
            f"DEMO gate failed: login={acct.get('login')} server={server!r} "
            f"trade_mode={trade_mode} is_demo={is_demo}. "
            "Require trade_mode DEMO and a demo server name (e.g. MetaQuotes-Demo)."
        )
    log.info(
        "DEMO gate OK login=%s server=%s trade_mode=%s equity=%.2f",
        acct.get("login"),
        server,
        trade_mode,
        float(acct.get("equity") or 0.0),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DEMO-only continuous MT5 signal host run (week-scale)"
    )
    parser.add_argument(
        "--strategy",
        choices=("trend", "breakout", "mean_rev", "all"),
        default="trend",
        help="Which StrategyEngine strategy drives orders (default: trend). "
        "'all' majority-votes BUY/SELL across the three strategies.",
    )
    dur = parser.add_mutually_exclusive_group()
    dur.add_argument(
        "--duration-days",
        type=float,
        default=None,
        help="Run length in days (default 7 if neither duration flag set)",
    )
    dur.add_argument(
        "--duration-seconds",
        type=float,
        default=None,
        help="Run length in seconds (for short tests)",
    )
    parser.add_argument(
        "--cycle-seconds",
        type=float,
        default=300.0,
        help="Seconds between evaluate cycles (default 300 = 5 min)",
    )
    parser.add_argument(
        "--max-positions",
        type=int,
        default=5,
        help="Max concurrent open positions (default 5)",
    )
    parser.add_argument(
        "--lot",
        type=float,
        default=DEFAULT_LOT,
        help=f"Order size (default {DEFAULT_LOT}, hard cap {LOT_CAP})",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=200,
        help="History bars for signals (default 200)",
    )
    parser.add_argument(
        "--manage-exits",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Close on signal flip / FLAT; keep on HOLD (default: on)",
    )
    args = parser.parse_args()

    if args.lot > LOT_CAP + 1e-12:
        print(
            f"ABORT: lot={args.lot} exceeds hard cap {LOT_CAP}.",
            file=sys.stderr,
        )
        return 2
    if args.lot <= 0:
        print("ABORT: lot must be > 0.", file=sys.stderr)
        return 2
    if args.cycle_seconds < 5:
        print("ABORT: --cycle-seconds must be >= 5.", file=sys.stderr)
        return 2
    if args.max_positions < 1:
        print("ABORT: --max-positions must be >= 1.", file=sys.stderr)
        return 2

    if args.duration_seconds is not None:
        duration_sec = float(args.duration_seconds)
    elif args.duration_days is not None:
        duration_sec = float(args.duration_days) * 86400.0
    else:
        duration_sec = 7.0 * 86400.0

    if duration_sec < 10:
        print("ABORT: duration must be >= 10 seconds.", file=sys.stderr)
        return 2

    lot = min(float(args.lot), LOT_CAP)
    log = _setup_logging()
    _write_pid()
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    env_path = _PROP_ALGO / ".env"
    _load_dotenv(env_path)

    log.info("=== DEMO signal WEEK run (host MT5, not Docker/mock) ===")
    log.info(
        "pid=%s duration_sec=%.0f (%.2f days) cycle_seconds=%.1f strategy=%s "
        "lot=%.2f max_positions=%d manage_exits=%s",
        os.getpid(),
        duration_sec,
        duration_sec / 86400.0,
        args.cycle_seconds,
        args.strategy,
        lot,
        args.max_positions,
        args.manage_exits,
    )
    log.info("log_file=%s pid_file=%s", _LOG_FILE, _PID_FILE)
    log.info(
        "Env file: %s (%s) summary=%s",
        env_path,
        "loaded" if env_path.is_file() else "missing",
        _safe_env_summary(),
    )

    from core.adapters.factory import create_adapter, get_broker_adapter_kind
    from core.registry.registry import Registry
    from trading.strategies.engine import StrategyEngine

    kind = get_broker_adapter_kind()
    if kind != "mt5":
        log.error(
            "ABORT: BROKER_ADAPTER=%r; set BROKER_ADAPTER=mt5 for this run.",
            kind,
        )
        _clear_pid()
        return 2

    symbols = _symbols_from_env()
    adapter = create_adapter("ACC1", kind="mt5")
    if not (os.getenv("MT5_SYMBOLS") or "").strip():
        adapter.symbols = list(symbols)

    log.info("Connecting MT5... symbols=%s", symbols)
    adapter.connect()
    started = time.time()
    deadline = started + duration_sec
    cycle = 0
    opens_placed = 0
    closes_done = 0
    try:
        acct = adapter.require_demo()
        _assert_demo_gate(acct, log)

        registry = Registry()
        registry.register_account("ACC1", adapter)
        engine = StrategyEngine(registry)

        while not _STOP and time.time() < deadline:
            cycle += 1
            remaining = max(0.0, deadline - time.time())
            cycle_orders: list[str] = []
            cycle_signals: list[str] = []
            cycle_actions: list[str] = []

            log.info(
                "--- Cycle %d start remaining=%.0fs (%.2fh) ---",
                cycle,
                remaining,
                remaining / 3600.0,
            )

            market_data = {}
            for symbol in symbols:
                try:
                    adapter.ensure_symbol(symbol)
                    market_data[symbol] = adapter.get_history(
                        symbol, lookback=args.lookback
                    )
                except Exception as exc:
                    cycle_actions.append(f"{symbol}:history_skip:{exc}")
                    log.warning("%s: SKIP history (%s)", symbol, exc)

            if market_data:
                signals = engine.run(market_data)
                try:
                    open_all = adapter.get_positions()
                except Exception as exc:
                    open_all = []
                    log.warning("get_positions failed: %s", exc)

                for symbol, acc_signals in signals.items():
                    primary = _primary_signal(acc_signals, args.strategy)
                    detail = {
                        name: (pack.get("signal") if isinstance(pack, dict) else pack)
                        for name, pack in acc_signals.items()
                    }
                    cycle_signals.append(f"{symbol}={primary}")
                    log.info(
                        "%s: primary=%s detail=%s",
                        symbol,
                        primary,
                        detail,
                    )

                    positions = [p for p in open_all if p["symbol"] == symbol]
                    same = [p for p in positions if p["side"] == primary]
                    opposite = [p for p in positions if p["side"] != primary]

                    if args.manage_exits and primary in FLAT_SIGNALS and positions:
                        for pos in positions:
                            try:
                                cres = adapter.close_position(pos["ticket"])
                                closes_done += 1
                                msg = (
                                    f"CLOSE_FLAT ticket={pos['ticket']} "
                                    f"was={pos['side']} res={cres.get('retcode', cres)}"
                                )
                                cycle_actions.append(f"{symbol}:{msg}")
                                log.info("%s: %s", symbol, msg)
                            except Exception as exc:
                                log.warning(
                                    "%s: SKIP close flat ticket=%s (%s)",
                                    symbol,
                                    pos["ticket"],
                                    exc,
                                )
                        continue

                    if primary in SKIP_SIGNALS:
                        cycle_actions.append(f"{symbol}:keep_hold")
                        continue

                    if primary not in TRADEABLE:
                        cycle_actions.append(f"{symbol}:skip_signal={primary}")
                        continue

                    if args.manage_exits and opposite:
                        close_failed = False
                        for pos in opposite:
                            try:
                                cres = adapter.close_position(pos["ticket"])
                                closes_done += 1
                                msg = (
                                    f"CLOSE_FLIP ticket={pos['ticket']} "
                                    f"was={pos['side']}->signal={primary} "
                                    f"res={cres.get('retcode', cres)}"
                                )
                                cycle_actions.append(f"{symbol}:{msg}")
                                log.info("%s: %s", symbol, msg)
                            except Exception as exc:
                                close_failed = True
                                log.warning(
                                    "%s: SKIP close flip ticket=%s (%s)",
                                    symbol,
                                    pos["ticket"],
                                    exc,
                                )
                                break
                        if close_failed:
                            continue
                        # Refresh count after closes.
                        try:
                            open_all = adapter.get_positions()
                        except Exception:
                            pass
                        positions = [p for p in open_all if p["symbol"] == symbol]
                        same = [p for p in positions if p["side"] == primary]

                    if same:
                        cycle_actions.append(f"{symbol}:already_{primary}")
                        continue

                    try:
                        open_all = adapter.get_positions()
                    except Exception as exc:
                        log.warning("%s: SKIP positions refresh (%s)", symbol, exc)
                        continue
                    if len(open_all) >= args.max_positions:
                        cycle_actions.append(
                            f"{symbol}:skip_max_positions={args.max_positions}"
                        )
                        log.info(
                            "%s: SKIP max positions (%d)",
                            symbol,
                            args.max_positions,
                        )
                        continue

                    try:
                        ores = adapter.place_order(
                            symbol, lot, None, None, side=primary
                        )
                        opens_placed += 1
                        msg = (
                            f"OPEN {primary} lot={lot} ticket={ores.get('ticket')} "
                            f"price={ores.get('price')}"
                        )
                        cycle_orders.append(f"{symbol}:{msg}")
                        cycle_actions.append(f"{symbol}:{msg}")
                        log.info("%s: %s", symbol, msg)
                        open_all = adapter.get_positions()
                    except Exception as exc:
                        cycle_actions.append(f"{symbol}:order_skip:{exc}")
                        log.warning("%s: SKIP order (%s)", symbol, exc)
            else:
                log.warning("No market data this cycle.")

            # Heartbeat
            try:
                acct_hb = adapter.get_account_info()
                equity = float(acct_hb.get("equity") or 0.0)
                balance = float(acct_hb.get("balance") or 0.0)
            except Exception as exc:
                equity = float("nan")
                balance = float("nan")
                log.warning("account_info heartbeat failed: %s", exc)
            try:
                positions_hb = adapter.get_positions()
            except Exception:
                positions_hb = []
            pos_summary = (
                ", ".join(
                    f"{p['symbol']}:{p['side']}:vol={p['volume']}:pnl={p['profit']:.2f}"
                    for p in positions_hb
                )
                or "(none)"
            )
            log.info(
                "HEARTBEAT cycle=%d equity=%.2f balance=%.2f open_positions=%d [%s] "
                "signals=[%s] orders_this_cycle=[%s] actions=[%s] "
                "totals opens=%d closes=%d elapsed_h=%.2f",
                cycle,
                equity,
                balance,
                len(positions_hb),
                pos_summary,
                "; ".join(cycle_signals) or "none",
                "; ".join(cycle_orders) or "none",
                "; ".join(cycle_actions) or "none",
                opens_placed,
                closes_done,
                (time.time() - started) / 3600.0,
            )

            if _STOP or time.time() >= deadline:
                break
            sleep_for = min(args.cycle_seconds, max(0.0, deadline - time.time()))
            if sleep_for <= 0:
                break
            log.info("sleeping %.1fs until next cycle...", sleep_for)
            # Interruptible sleep
            end_sleep = time.time() + sleep_for
            while not _STOP and time.time() < end_sleep:
                time.sleep(min(1.0, end_sleep - time.time()))

        reason = "stop_requested" if _STOP else "duration_elapsed"
        try:
            acct_after = adapter.get_account_info()
            equity_after = float(acct_after.get("equity") or 0.0)
            open_positions = adapter.get_positions()
        except Exception as exc:
            equity_after = float("nan")
            open_positions = []
            log.warning("final account snapshot failed: %s", exc)

        log.info("=== WEEK RUN END reason=%s cycles=%d ===", reason, cycle)
        log.info(
            "opens_placed=%d closes_done=%d equity_end=%.2f open_positions=%d",
            opens_placed,
            closes_done,
            equity_after,
            len(open_positions),
        )
        for p in open_positions:
            log.info(
                "  ticket=%s %s %s vol=%s pnl=%.2f",
                p.get("ticket"),
                p.get("symbol"),
                p.get("side"),
                p.get("volume"),
                float(p.get("profit") or 0.0),
            )
        log.info("Done at %s", _utc_now())
        return 0
    except Exception as exc:
        log.exception("FATAL: %s", exc)
        return 1
    finally:
        try:
            adapter.close()
        except Exception:
            pass
        _clear_pid()


if __name__ == "__main__":
    raise SystemExit(main())
