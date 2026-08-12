#!/usr/bin/env python3
"""DEMO-only short host run: StrategyEngine signals -> tiny MT5 market orders.

Mode: ~3 cycles with ~15s sleep (~45–60s total), not a long hang.
Does NOT use Docker/mock. Aborts unless the MT5 account is DEMO.
Never logs passwords.

Usage (from repo root, Windows host with MetaTrader 5 running):

  python prop_algo/deploy/demo_signal_run.py
  python prop_algo/deploy/demo_signal_run.py --strategy trend --cycles 3

Loads prop_algo/.env if present (MT5_LOGIN / MT5_PASSWORD / MT5_SERVER).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Allow `python prop_algo/deploy/demo_signal_run.py` from repo root.
_PROP_ALGO = Path(__file__).resolve().parents[1]
_REPO_ROOT = _PROP_ALGO.parent
for _p in (_REPO_ROOT, _PROP_ALGO):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)

LOT = 0.01
DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD")
TRADEABLE = frozenset({"BUY", "SELL"})
SKIP_SIGNALS = frozenset({"HOLD", "FLAT", "NONE", ""})


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


def main() -> int:
    parser = argparse.ArgumentParser(description="DEMO-only MT5 signal host run")
    parser.add_argument(
        "--strategy",
        choices=("trend", "breakout", "mean_rev", "all"),
        default="trend",
        help="Which StrategyEngine strategy drives orders (default: trend). "
        "'all' majority-votes BUY/SELL across the three strategies.",
    )
    parser.add_argument("--cycles", type=int, default=3, help="Evaluate cycles (default 3)")
    parser.add_argument(
        "--sleep",
        type=float,
        default=15.0,
        help="Seconds between cycles (default 15)",
    )
    parser.add_argument(
        "--max-opens",
        type=int,
        default=3,
        help="Max new market opens this run (default 3)",
    )
    parser.add_argument("--lot", type=float, default=LOT, help="Order size (default 0.01)")
    parser.add_argument(
        "--lookback",
        type=int,
        default=200,
        help="History bars for signals (default 200)",
    )
    args = parser.parse_args()

    if args.lot > 0.05:
        print("ABORT: lot too large for demo script (max 0.05).", file=sys.stderr)
        return 2
    if args.cycles < 1:
        print("ABORT: cycles must be >= 1.", file=sys.stderr)
        return 2

    env_path = _PROP_ALGO / ".env"
    _load_dotenv(env_path)
    print("=== DEMO signal run (host MT5, not Docker/mock) ===")
    print(f"Mode: {args.cycles} cycles, sleep={args.sleep}s (~"
          f"{int(args.cycles * args.sleep)}s wall), strategy={args.strategy}")
    print(f"Env file: {env_path} ({'loaded' if env_path.is_file() else 'missing'})")
    print(f"Env summary (no secrets): {_safe_env_summary()}")

    from core.adapters.factory import create_adapter, get_broker_adapter_kind
    from core.registry.registry import Registry
    from trading.strategies.engine import StrategyEngine

    kind = get_broker_adapter_kind()
    if kind != "mt5":
        print(
            f"ABORT: BROKER_ADAPTER={kind!r}; set BROKER_ADAPTER=mt5 for this run.",
            file=sys.stderr,
        )
        return 2

    symbols = _symbols_from_env()
    adapter = create_adapter("ACC1", kind="mt5")
    # Prefer CLI/default watchlist if env only had two symbols.
    if not (os.getenv("MT5_SYMBOLS") or "").strip():
        adapter.symbols = list(symbols)

    print("Connecting MT5...")
    adapter.connect()
    try:
        acct = adapter.require_demo()
        equity_before = float(acct["equity"])
        print(
            f"DEMO OK login={acct['login']} server={acct['server']} "
            f"equity_before={equity_before:.2f}"
        )

        registry = Registry()
        registry.register_account("ACC1", adapter)
        engine = StrategyEngine(registry)

        opens_placed = 0
        orders: list[dict] = []
        closes: list[dict] = []
        skipped: list[dict] = []
        all_signals: list[dict] = []

        for cycle in range(1, args.cycles + 1):
            print(f"\n--- Cycle {cycle}/{args.cycles} ---")
            market_data = {}
            for symbol in symbols:
                try:
                    adapter.ensure_symbol(symbol)
                    market_data[symbol] = adapter.get_history(symbol, lookback=args.lookback)
                except Exception as exc:
                    skipped.append(
                        {"cycle": cycle, "symbol": symbol, "reason": f"history: {exc}"}
                    )
                    print(f"  {symbol}: SKIP history ({exc})")

            if not market_data:
                print("  No market data this cycle.")
            else:
                # StrategyEngine expects account-keyed history from registry normally;
                # feed per-symbol frames directly (same generate_signals API).
                signals = engine.run(market_data)
                for symbol, acc_signals in signals.items():
                    primary = _primary_signal(acc_signals, args.strategy)
                    snap = {
                        "cycle": cycle,
                        "symbol": symbol,
                        "primary": primary,
                        "strategies": {
                            name: (pack.get("signal") if isinstance(pack, dict) else pack)
                            for name, pack in acc_signals.items()
                        },
                    }
                    all_signals.append(snap)
                    print(
                        f"  {symbol}: primary={primary} "
                        f"detail={snap['strategies']}"
                    )

                    if primary in SKIP_SIGNALS or primary not in TRADEABLE:
                        skipped.append(
                            {
                                "cycle": cycle,
                                "symbol": symbol,
                                "reason": f"signal={primary}",
                            }
                        )
                        continue

                    try:
                        positions = adapter.get_positions(symbol)
                    except Exception as exc:
                        skipped.append(
                            {
                                "cycle": cycle,
                                "symbol": symbol,
                                "reason": f"positions: {exc}",
                            }
                        )
                        print(f"  {symbol}: SKIP positions ({exc})")
                        continue

                    same = [p for p in positions if p["side"] == primary]
                    opposite = [p for p in positions if p["side"] != primary]

                    if same:
                        skipped.append(
                            {
                                "cycle": cycle,
                                "symbol": symbol,
                                "reason": f"already {primary}",
                            }
                        )
                        print(f"  {symbol}: SKIP already in {primary}")
                        continue

                    if opens_placed >= args.max_opens:
                        skipped.append(
                            {
                                "cycle": cycle,
                                "symbol": symbol,
                                "reason": f"max_opens={args.max_opens}",
                            }
                        )
                        print(f"  {symbol}: SKIP max opens reached")
                        continue

                    close_failed = False
                    for pos in opposite:
                        try:
                            cres = adapter.close_position(pos["ticket"])
                            closes.append(
                                {
                                    "cycle": cycle,
                                    "symbol": symbol,
                                    "closed_ticket": pos["ticket"],
                                    "was": pos["side"],
                                    "result": cres,
                                }
                            )
                            print(
                                f"  {symbol}: closed opposite ticket={pos['ticket']} "
                                f"({pos['side']})"
                            )
                        except Exception as exc:
                            skipped.append(
                                {
                                    "cycle": cycle,
                                    "symbol": symbol,
                                    "reason": f"close opposite: {exc}",
                                }
                            )
                            print(f"  {symbol}: SKIP close opposite ({exc})")
                            close_failed = True
                            break
                    if close_failed:
                        continue

                    try:
                        ores = adapter.place_order(
                            symbol, args.lot, None, None, side=primary
                        )
                        opens_placed += 1
                        orders.append(
                            {
                                "cycle": cycle,
                                "symbol": symbol,
                                "side": primary,
                                "lot": args.lot,
                                "ticket": ores.get("ticket"),
                                "price": ores.get("price"),
                                "result": ores,
                            }
                        )
                        print(
                            f"  {symbol}: OPEN {primary} lot={args.lot} "
                            f"ticket={ores.get('ticket')} price={ores.get('price')}"
                        )
                    except Exception as exc:
                        skipped.append(
                            {
                                "cycle": cycle,
                                "symbol": symbol,
                                "reason": f"order: {exc}",
                            }
                        )
                        print(f"  {symbol}: SKIP order ({exc})")

            if cycle < args.cycles:
                print(f"  sleeping {args.sleep}s...")
                time.sleep(args.sleep)

        acct_after = adapter.get_account_info()
        equity_after = float(acct_after["equity"])
        open_positions = adapter.get_positions()

        print("\n=== REPORT ===")
        print(f"Strategy (primary): {args.strategy}")
        print(f"Cycles: {args.cycles} x sleep {args.sleep}s")
        print(f"Equity before: {equity_before:.2f}")
        print(f"Equity after:  {equity_after:.2f}")
        print(f"Signals seen ({len(all_signals)}):")
        for s in all_signals:
            print(
                f"  c{s['cycle']} {s['symbol']}: primary={s['primary']} "
                f"{s['strategies']}"
            )
        print(f"Orders placed ({len(orders)}):")
        if not orders:
            print("  (none)")
        for o in orders:
            print(
                f"  c{o['cycle']} {o['symbol']} {o['side']} lot={o['lot']} "
                f"ticket={o['ticket']} price={o['price']}"
            )
        print(f"Opposite closes ({len(closes)}):")
        if not closes:
            print("  (none)")
        for c in closes:
            print(
                f"  c{c['cycle']} {c['symbol']} closed={c['closed_ticket']} "
                f"was={c['was']}"
            )
        print(f"Skipped ({len(skipped)}):")
        if not skipped:
            print("  (none)")
        for sk in skipped:
            print(f"  c{sk['cycle']} {sk['symbol']}: {sk['reason']}")
        print(f"Open positions at end ({len(open_positions)}):")
        if not open_positions:
            print("  (none)")
        for p in open_positions:
            print(
                f"  ticket={p['ticket']} {p['symbol']} {p['side']} "
                f"vol={p['volume']} pnl={p['profit']:.2f}"
            )
        print("Done.")
        return 0
    finally:
        adapter.close()


if __name__ == "__main__":
    raise SystemExit(main())
