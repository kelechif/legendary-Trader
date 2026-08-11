"""0DTE execution orchestrator for Moomoo."""

from __future__ import annotations

from datetime import datetime

from services.execution_engine.moomoo_options_broker import (
    close_credit_vertical_combo,
    get_option_positions,
    place_credit_vertical_combo,
    use_moomoo_options,
)
from services.execution_engine.ts_bridge import trading_halted
from services.options_engine.moomoo_chain import (
    credit_for_vertical,
    get_execution_contracts,
    get_zero_dte_chain_info,
    pick_contracts_for_vertical,
)
from services.options_engine.zero_dte_stop import should_stop_vertical
from services.shared.config import OPTIONS_CFG
from services.shared import log_channels


def _in_window(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    t = now.hour * 100 + now.minute
    windows = OPTIONS_CFG.get("windows", {})
    for key in ("morning", "afternoon", "midday"):
        w = windows.get(key, {})
        if not w.get("enabled", key == "morning"):
            continue
        start = _hhmm(w.get("start", "09:45"))
        end = _hhmm(w.get("end", "10:15"))
        if start <= t <= end:
            return True
    return False


def _hhmm(s: str) -> int:
    s = str(s).replace(":", "")
    return int(s[:4])


def _max_tickets() -> int:
    return int(OPTIONS_CFG.get("risk", {}).get("max_tickets_per_day", 3))


def execute_0dte_signal(direction: str, *, tickets_used: int = 0) -> dict:
    """
    Execute one 0DTE credit vertical on Moomoo.
    direction: bullish | bearish (from ZeroDTERegime BUY/SELL)
    """
    if not use_moomoo_options():
        return {"status": "skipped", "reason": "moomoo_options_not_configured"}

    if trading_halted():
        return {"status": "skipped", "reason": "kill_switch"}

    if not _in_window():
        return {"status": "skipped", "reason": "outside_window"}

    if tickets_used >= _max_tickets():
        return {"status": "skipped", "reason": "max_tickets_per_day"}

    mm = OPTIONS_CFG.get("moomoo", {})
    owner = str(mm.get("underlying", "US.SPY"))
    short_delta = float(mm.get("short_delta", 0.12))
    width = float(mm.get("spread_width", 5.0))
    qty = int(mm.get("contracts_per_trade", 1))
    credit = mm.get("limit_credit")

    contracts, chain_source = get_execution_contracts(owner)
    if contracts.empty:
        return {"status": "skipped", "reason": "no_0dte_chain", "owner": owner, "chain_source": chain_source}

    from services.options_engine.moomoo_intraday import fetch_intraday_candles

    bars = fetch_intraday_candles(owner, days_back=1, max_bars=5)
    spot = float(bars[-1]["close"]) if bars else None

    legs = pick_contracts_for_vertical(
        contracts,
        direction,
        short_delta=short_delta,
        width=width,
        spot=spot,
    )
    if not legs:
        return {"status": "skipped", "reason": "no_matching_contracts", "owner": owner}

    short_leg, long_leg = legs
    credit_val, credit_source = credit_for_vertical(
        contracts, short_leg, long_leg, width=width, short_delta=short_delta
    )
    limit = float(credit) if credit else credit_val

    order = place_credit_vertical_combo(
        short_leg["code"],
        long_leg["code"],
        qty=qty,
        price=limit,
        order_type=str(mm.get("order_type", "NORMAL")),
    )

    log_channels.log_event(
        "execution",
        "0dte_vertical",
        owner=owner,
        direction=direction,
        short=short_leg,
        long=long_leg,
        credit=credit_val,
        credit_source=credit_source,
        order_status=order.get("status"),
    )
    return {
        "status": order.get("status", "ok"),
        "owner": owner,
        "direction": direction,
        "short_leg": short_leg,
        "long_leg": long_leg,
        "credit": credit_val,
        "credit_source": credit_source,
        "chain_source": chain_source,
        "order": order,
    }


def check_and_close_stops(bar: dict, open_trades: list[dict]) -> tuple[list[dict], list[dict]]:
    """Evaluate open trades; close any that hit intraday stop."""
    from services.options_engine.zero_dte_stop import legs_from_trade

    spot = float(bar.get("close", 0))
    closed: list[dict] = []
    remaining: list[dict] = []
    mm = OPTIONS_CFG.get("moomoo", {})
    qty = int(mm.get("contracts_per_trade", 1))

    for trade in open_trades:
        legs = legs_from_trade(trade)
        if not legs:
            remaining.append(trade)
            continue
        if trade.get("direction") == "bullish":
            adverse = float(bar.get("low", spot))
        else:
            adverse = float(bar.get("high", spot))
        hit, mtm = should_stop_vertical(
            legs,
            float(trade.get("credit", 0)),
            spot,
            adverse_spot=adverse,
            contracts=qty,
        )
        if not hit:
            remaining.append(trade)
            continue
        close = close_credit_vertical_combo(
            trade["short_code"],
            trade["long_code"],
            qty=qty,
        )
        record = {**trade, "exit_reason": "stop_loss", "mtm_pnl": mtm, "close_order": close}
        closed.append(record)
        log_channels.log_event("execution", "0dte_stop_close", **record)

    return remaining, closed


def session_status() -> dict:
    mm = OPTIONS_CFG.get("moomoo", {})
    return {
        "broker": "moomoo",
        "underlying": mm.get("underlying", "US.SPY"),
        "in_window": _in_window(),
        "halted": trading_halted(),
        "safe_mode": mm.get("safe_mode", True),
        "open_option_positions": len(get_option_positions()),
        "chain_info": get_zero_dte_chain_info(),
    }
