"""0DTE backtest — simple fixed-credit mode."""

from __future__ import annotations

from collections import defaultdict

from services.options_engine.chain import pick_vertical_strikes
from services.options_engine.pnl import simulate_vertical_settle
from services.shared.config import OPTIONS_CFG, get_strategy_params
from services.strategy_engine.registry import choose_signal


def _day_key(time_key: str) -> str:
    return str(time_key)[:10].replace("-", "")


def _signal_direction(signal: str) -> str | None:
    if signal == "BUY":
        return "bullish"
    if signal == "SELL":
        return "bearish"
    return None


def run_regime_backtest(
    candles: list[dict],
    *,
    width: float = 5.0,
    credit: float = 0.50,
    multiplier: float = 100.0,
) -> dict:
    """One 0DTE credit vertical per day on first ZeroDTERegime signal; settle at close."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for c in candles:
        tk = c.get("time_key", "")
        if tk:
            by_day[_day_key(tk)].append(c)

    params = get_strategy_params("ZeroDTERegime") or {}
    days_out = []
    history: list[dict] = []

    for day in sorted(by_day.keys()):
        day_bars = by_day[day]
        if len(day_bars) < 55:
            continue

        traded = False
        for i in range(55, len(day_bars)):
            window = history + day_bars[: i + 1]
            signal = choose_signal("ZeroDTERegime", [], params, window)
            direction = _signal_direction(signal)
            if not direction:
                continue

            entry_bar = day_bars[i]
            exit_bar = day_bars[-1]
            spot_entry = float(entry_bar["close"])
            spot_exit = float(exit_bar["close"])
            legs = pick_vertical_strikes(spot_entry, direction, width)
            pnl = simulate_vertical_settle(legs, spot_exit, credit, multiplier=multiplier)
            days_out.append(
                {
                    "date": day,
                    "signal": signal,
                    "direction": direction,
                    "entry_time": entry_bar.get("time_key"),
                    "spot_entry": round(spot_entry, 2),
                    "spot_exit": round(spot_exit, 2),
                    "short_strike": legs.short_strike,
                    "long_strike": legs.long_strike,
                    "pnl": round(pnl, 2),
                }
            )
            traded = True
            break

        history.extend(day_bars)
        if len(history) > 300:
            history = history[-300:]

        if not traded:
            days_out.append({"date": day, "signal": "HOLD", "pnl": 0.0, "traded": False})

    active = [d for d in days_out if "direction" in d]
    wins = sum(1 for d in active if d["pnl"] > 0)
    total = sum(d["pnl"] for d in active)
    n = len(active)

    return {
        "mode": "simple",
        "underlying": OPTIONS_CFG.get("moomoo", {}).get("underlying", "US.SPY"),
        "strategy": "ZeroDTERegime",
        "structure": "credit_vertical",
        "width": width,
        "credit": credit,
        "multiplier": multiplier,
        "session_days": len(by_day),
        "trades": n,
        "total_pnl": round(total, 2),
        "avg_pnl": round(total / n, 2) if n else 0.0,
        "win_rate": round(wins / n, 4) if n else 0.0,
        "days": days_out,
    }
