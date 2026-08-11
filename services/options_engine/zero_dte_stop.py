"""Intraday stop-loss for open 0DTE credit verticals."""

from __future__ import annotations

from services.options_engine.chain import VerticalLegs
from services.options_engine.pnl import spread_liability_per_share
from services.shared.config import OPTIONS_CFG


def stop_loss_multiple() -> float:
    bt = OPTIONS_CFG.get("backtest", {})
    mm = OPTIONS_CFG.get("moomoo", {})
    return float(bt.get("stop_loss_credit_multiple", mm.get("stop_loss_credit_multiple", 2.0)))


def should_stop_vertical(
    legs: VerticalLegs,
    credit: float,
    spot: float,
    *,
    adverse_spot: float | None = None,
    multiplier: float = 100.0,
    contracts: int = 1,
    stop_multiple: float | None = None,
) -> tuple[bool, float]:
    """
    True when MTM loss >= stop_multiple × credit collected.
    adverse_spot: bar low (puts) or high (calls); defaults to spot.
    """
    stop_mult = stop_multiple if stop_multiple is not None else stop_loss_multiple()
    check = adverse_spot if adverse_spot is not None else spot
    liability = spread_liability_per_share(legs, check)
    pnl = (credit - liability) * multiplier * contracts
    threshold = -stop_mult * credit * multiplier * contracts
    return pnl <= threshold, round(pnl, 2)


def legs_from_trade(trade: dict) -> VerticalLegs | None:
    try:
        direction = trade.get("direction", "bullish")
        opt_dir = "put" if direction in ("bullish", "bull", "buy") else "call"
        return VerticalLegs(
            underlying=float(trade.get("spot_entry", 0)),
            short_strike=float(trade["short_strike"]),
            long_strike=float(trade["long_strike"]),
            direction=opt_dir,
            width=abs(float(trade["short_strike"]) - float(trade["long_strike"])),
        )
    except (KeyError, TypeError, ValueError):
        return None
