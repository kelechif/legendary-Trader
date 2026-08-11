"""P&L simulation for simplified 0DTE structures."""

from __future__ import annotations

from services.options_engine.chain import VerticalLegs, pin_payoff


def simulate_vertical_settle(
    legs: VerticalLegs,
    spot_at_close: float,
    credit_received: float,
    contracts: int = 1,
    multiplier: float = 100.0,
) -> float:
    """Credit vertical P&L at cash settlement."""
    short_intr = pin_payoff(spot_at_close, legs.short_strike, legs.direction)
    long_intr = pin_payoff(spot_at_close, legs.long_strike, legs.direction)
    spread_liability = max(short_intr - long_intr, 0.0)
    pnl_per = credit_received - spread_liability
    return pnl_per * multiplier * contracts


def simulate_fly_settle(
    center: float,
    wing_width: float,
    spot_at_close: float,
    net_debit: float,
    contracts: int = 1,
    multiplier: float = 100.0,
) -> float:
    """Symmetric long butterfly payoff minus net debit."""
    lower = center - wing_width
    upper = center + wing_width
    if spot_at_close <= lower or spot_at_close >= upper:
        payoff = 0.0
    elif spot_at_close <= center:
        payoff = spot_at_close - lower
    else:
        payoff = upper - spot_at_close
    return (payoff - net_debit) * multiplier * contracts


def spread_liability_per_share(legs: VerticalLegs, spot: float) -> float:
    short_intr = pin_payoff(spot, legs.short_strike, legs.direction)
    long_intr = pin_payoff(spot, legs.long_strike, legs.direction)
    return max(short_intr - long_intr, 0.0)


def vertical_path_detail(
    legs: VerticalLegs,
    bars_after_entry: list[dict],
    credit_received: float,
    *,
    width: float | None = None,
    stop_loss_credit_multiple: float = 2.0,
    multiplier: float = 100.0,
    contracts: int = 1,
) -> dict:
    """
    Walk intraday bars after entry; stop if MTM loss exceeds stop_loss_credit_multiple × credit.
    Uses adverse extreme per bar (low for puts, high for calls).
    """
    w = width if width is not None else legs.width
    stop_threshold_pnl = -stop_loss_credit_multiple * credit_received * multiplier * contracts

    exit_bar = bars_after_entry[-1] if bars_after_entry else None
    exit_spot = float(exit_bar["close"]) if exit_bar else 0.0
    exit_reason = "expire"
    exit_time = exit_bar.get("time_key") if exit_bar else None

    for bar in bars_after_entry:
        if legs.direction == "put":
            adverse = float(bar.get("low", bar["close"]))
        else:
            adverse = float(bar.get("high", bar["close"]))
        liability = spread_liability_per_share(legs, adverse)
        pnl = (credit_received - liability) * multiplier * contracts
        if pnl <= stop_threshold_pnl:
            exit_bar = bar
            exit_spot = float(bar["close"])
            exit_reason = "stop_loss"
            exit_time = bar.get("time_key")
            break

    detail = vertical_settle_detail(
        legs,
        exit_spot,
        credit_received,
        width=w,
        multiplier=multiplier,
        contracts=contracts,
    )
    detail["exit_reason"] = exit_reason
    detail["exit_time"] = exit_time
    detail["spot_exit"] = round(exit_spot, 2)
    detail["stop_threshold_pnl"] = round(stop_threshold_pnl, 2)
    if exit_reason == "stop_loss":
        detail["outcome"] = "stopped"
    return detail


def vertical_settle_detail(
    legs: VerticalLegs,
    spot_at_close: float,
    credit_received: float,
    *,
    width: float | None = None,
    contracts: int = 1,
    multiplier: float = 100.0,
) -> dict:
    """Credit vertical settlement with max-loss and outcome label."""
    w = width if width is not None else legs.width
    short_intr = pin_payoff(spot_at_close, legs.short_strike, legs.direction)
    long_intr = pin_payoff(spot_at_close, legs.long_strike, legs.direction)
    spread_liability = max(short_intr - long_intr, 0.0)
    pnl_per = credit_received - spread_liability
    pnl = round(pnl_per * multiplier * contracts, 2)
    max_loss = round(max(0.0, (w - credit_received) * multiplier * contracts), 2)
    liability = round(spread_liability * multiplier * contracts, 2)

    if pnl > 0.01:
        outcome = "win"
    elif pnl < -0.01:
        outcome = "loss"
    else:
        outcome = "breakeven"

    risk_pct = round((pnl / max_loss * 100) if max_loss > 0 else 0.0, 1)

    return {
        "pnl": pnl,
        "max_loss": max_loss,
        "liability": liability,
        "outcome": outcome,
        "pnl_pct_of_max_risk": risk_pct,
    }
