"""Strike selection helpers for 0DTE vertical / fly structures."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class VerticalLegs:
    underlying: float
    short_strike: float
    long_strike: float
    direction: str  # "put" | "call"
    width: float


def expected_move(spot: float, iv: float, minutes_to_close: float = 390) -> float:
    """Approximate 1-sigma move to expiry (annualized IV, minutes in session)."""
    if spot <= 0 or iv <= 0:
        return 0.0
    t_years = max(minutes_to_close, 1) / (252 * 390)
    return spot * iv * math.sqrt(t_years)


def pick_vertical_strikes(
    spot: float,
    direction: str,
    width: float,
    otm_pct: float = 0.003,
) -> VerticalLegs:
    """
    Pick round strikes for a credit vertical.
    direction: bullish -> sell put spread below spot; bearish -> sell call spread above.
    """
    direction = direction.lower()
    if direction in ("bull", "bullish", "long", "1"):
        short = round(spot * (1 - otm_pct), 0)
        long = short - width
        leg_dir = "put"
    else:
        short = round(spot * (1 + otm_pct), 0)
        long = short + width
        leg_dir = "call"
    return VerticalLegs(
        underlying=spot,
        short_strike=short,
        long_strike=long,
        direction=leg_dir,
        width=width,
    )


def pin_payoff(spot_at_close: float, strike: float, option_type: str) -> float:
    """Intrinsic at expiry (per share / index point)."""
    if option_type == "put":
        return max(strike - spot_at_close, 0.0)
    return max(spot_at_close - strike, 0.0)
