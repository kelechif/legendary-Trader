"""Realistic 0DTE credit-vertical backtest with chain credits and max-loss."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from services.options_engine.chain import VerticalLegs, pick_vertical_strikes
from services.options_engine.moomoo_chain import (
    credit_for_vertical,
    get_chain_for_backtest_date,
    pick_contracts_for_vertical,
)
from services.options_engine.pnl import vertical_path_detail
from services.shared.config import OPTIONS_CFG, get_strategy_params
from services.strategy_engine.registry import choose_signal


def _day_key(time_key: str) -> str:
    return str(time_key)[:10].replace("-", "")


def _iso_day(day_key: str) -> str:
    return f"{day_key[:4]}-{day_key[4:6]}-{day_key[6:8]}"


def _signal_direction(signal: str) -> str | None:
    if signal == "BUY":
        return "bullish"
    if signal == "SELL":
        return "bearish"
    return None


def _regime_params() -> dict:
    defaults = {
        "morning_start": 945,
        "morning_end": 1015,
        "afternoon_start": 1430,
        "afternoon_end": 1515,
        "use_morning": True,
        "use_afternoon": True,
        "vix_max": 28.0,
        "sma_regime": 50,
    }
    defaults.update(get_strategy_params("ZeroDTERegime") or {})
    return defaults


def _backtest_cfg() -> dict:
    defaults = {
        "stop_loss_credit_multiple": 2.0,
        "use_live_chain_today": True,
    }
    defaults.update(OPTIONS_CFG.get("backtest", {}))
    return defaults


def _active_window(time_hhmm: int, params: dict) -> str | None:
    if params.get("use_morning", True) and params["morning_start"] <= time_hhmm <= params["morning_end"]:
        return "morning"
    if params.get("use_afternoon", True) and params["afternoon_start"] <= time_hhmm <= params["afternoon_end"]:
        return "afternoon"
    return None


def run_realistic_backtest(
    candles: list[dict],
    *,
    owner: str | None = None,
    width: float = 5.0,
    short_delta: float = 0.12,
    max_trades_per_day: int = 2,
    multiplier: float = 100.0,
    use_live_chain_for_today: bool | None = None,
    stop_loss_credit_multiple: float | None = None,
) -> dict:
    """
    ZeroDTERegime backtest with morning + afternoon windows.
    Credit from live OpenD 0DTE chain (today) or estimate; intraday stop-loss optional.
    """
    owner = owner or OPTIONS_CFG.get("moomoo", {}).get("underlying", "US.SPY")
    params = _regime_params()
    bt_cfg = _backtest_cfg()
    sma_len = int(params.get("sma_regime", 50))
    use_live = bt_cfg["use_live_chain_today"] if use_live_chain_for_today is None else use_live_chain_for_today
    stop_mult = float(
        stop_loss_credit_multiple
        if stop_loss_credit_multiple is not None
        else bt_cfg["stop_loss_credit_multiple"]
    )
    today_iso = date.today().isoformat()

    by_day: dict[str, list[dict]] = defaultdict(list)
    for c in candles:
        tk = c.get("time_key", "")
        if tk:
            by_day[_day_key(tk)].append(c)

    trades: list[dict] = []
    history: list[dict] = []
    chain_cache: dict[str, tuple] = {}
    chain_sources: dict[str, int] = defaultdict(int)

    for day in sorted(by_day.keys()):
        day_bars = by_day[day]
        if len(day_bars) < max(55, sma_len + 1):
            continue

        iso = _iso_day(day)
        if iso not in chain_cache:
            chain_cache[iso] = get_chain_for_backtest_date(owner, iso, use_live_today=use_live)
        chain_df, chain_kind = chain_cache[iso]
        chain_sources[chain_kind] += 1

        windows_used: set[str] = set()

        for i in range(max(55, sma_len), len(day_bars)):
            if len(windows_used) >= max_trades_per_day:
                break

            bar = day_bars[i]
            wname = _active_window(int(bar.get("time_hhmm", 0)), params)
            if not wname or wname in windows_used:
                continue

            window_candles = history + day_bars[: i + 1]
            signal = choose_signal("ZeroDTERegime", [], params, window_candles)
            direction = _signal_direction(signal)
            if not direction:
                continue

            spot_entry = float(bar["close"])
            short_code = long_code = None

            picked = None
            if chain_df is not None and not chain_df.empty:
                picked = pick_contracts_for_vertical(
                    chain_df,
                    direction,
                    short_delta=short_delta,
                    width=width,
                )

            if picked:
                short_leg, long_leg = picked
                legs_obj = VerticalLegs(
                    underlying=spot_entry,
                    short_strike=short_leg["strike"],
                    long_strike=long_leg["strike"],
                    direction="put" if direction == "bullish" else "call",
                    width=abs(short_leg["strike"] - long_leg["strike"]),
                )
                credit, credit_source = credit_for_vertical(
                    chain_df, short_leg, long_leg, width=width, short_delta=short_delta
                )
                short_code = short_leg.get("code")
                long_code = long_leg.get("code")
                if chain_kind == "live_0dte" and credit_source == "estimate":
                    credit_source = "live_0dte_estimate"
                elif chain_kind in ("live_0dte", "chain_today", "chain_historical"):
                    credit_source = f"{chain_kind}:{credit_source}"
            else:
                legs_obj = pick_vertical_strikes(spot_entry, direction, width)
                credit, credit_source = credit_for_vertical(
                    None, {}, {}, width=width, short_delta=short_delta
                )

            detail = vertical_path_detail(
                legs_obj,
                day_bars[i:],
                credit,
                width=width,
                stop_loss_credit_multiple=stop_mult,
                multiplier=multiplier,
            )

            trades.append(
                {
                    "date": day,
                    "window": wname,
                    "signal": signal,
                    "direction": direction,
                    "entry_time": bar.get("time_key"),
                    "exit_time": detail.get("exit_time"),
                    "exit_reason": detail.get("exit_reason"),
                    "spot_entry": round(spot_entry, 2),
                    "spot_exit": detail.get("spot_exit"),
                    "short_strike": legs_obj.short_strike,
                    "long_strike": legs_obj.long_strike,
                    "short_code": short_code,
                    "long_code": long_code,
                    "credit": round(credit, 2),
                    "credit_source": credit_source,
                    "chain_kind": chain_kind,
                    "pnl": detail["pnl"],
                    "max_loss": detail["max_loss"],
                    "liability": detail["liability"],
                    "outcome": detail["outcome"],
                    "pnl_pct_of_max_risk": detail["pnl_pct_of_max_risk"],
                    "stop_threshold_pnl": detail.get("stop_threshold_pnl"),
                }
            )
            windows_used.add(wname)

        history.extend(day_bars)
        if len(history) > 400:
            history = history[-400:]

    n = len(trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] < 0)
    stopped = sum(1 for t in trades if t.get("exit_reason") == "stop_loss")
    total = sum(t["pnl"] for t in trades)
    max_dd = 0.0
    peak = 0.0
    cum = 0.0
    for t in trades:
        cum += t["pnl"]
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    return {
        "mode": "realistic",
        "underlying": owner,
        "strategy": "ZeroDTERegime",
        "structure": "credit_vertical",
        "width": width,
        "short_delta": short_delta,
        "multiplier": multiplier,
        "stop_loss_credit_multiple": stop_mult,
        "use_live_chain_today": use_live,
        "today": today_iso,
        "session_days": len(by_day),
        "trades": n,
        "wins": wins,
        "losses": losses,
        "stopped_out": stopped,
        "breakeven": n - wins - losses,
        "total_pnl": round(total, 2),
        "avg_pnl": round(total / n, 2) if n else 0.0,
        "win_rate": round(wins / n, 4) if n else 0.0,
        "max_drawdown": round(max_dd, 2),
        "chain_sources": dict(chain_sources),
        "trades_list": trades,
    }
