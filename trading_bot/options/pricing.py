"""Black-Scholes European option pricing and Greeks (stdlib only, no scipy)."""
from __future__ import annotations

import math


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _intrinsic(spot: float, strike: float, right: str) -> float:
    return max(spot - strike, 0.0) if right == "call" else max(strike - spot, 0.0)


def bs_price(spot: float, strike: float, years_to_expiry: float, risk_free_rate: float,
             sigma: float, right: str = "call") -> float:
    """Theoretical option price. Degenerates to intrinsic value at/after expiry
    or when volatility is non-positive."""
    if years_to_expiry <= 0 or sigma <= 0 or spot <= 0 or strike <= 0:
        return _intrinsic(spot, strike, right)

    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * sigma ** 2) * years_to_expiry) / (
        sigma * math.sqrt(years_to_expiry)
    )
    d2 = d1 - sigma * math.sqrt(years_to_expiry)
    discount = math.exp(-risk_free_rate * years_to_expiry)

    if right == "call":
        return spot * _norm_cdf(d1) - strike * discount * _norm_cdf(d2)
    return strike * discount * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def bs_greeks(spot: float, strike: float, years_to_expiry: float, risk_free_rate: float,
              sigma: float, right: str = "call") -> dict:
    """Delta, gamma, theta (per calendar day), vega (per 1 vol point), rho."""
    if years_to_expiry <= 0 or sigma <= 0 or spot <= 0 or strike <= 0:
        intrinsic_delta = 1.0 if (right == "call" and spot > strike) else (
            -1.0 if (right == "put" and spot < strike) else 0.0
        )
        return {"delta": intrinsic_delta, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

    sqrt_t = math.sqrt(years_to_expiry)
    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * sigma ** 2) * years_to_expiry) / (
        sigma * sqrt_t
    )
    d2 = d1 - sigma * sqrt_t
    discount = math.exp(-risk_free_rate * years_to_expiry)
    pdf_d1 = _norm_pdf(d1)

    gamma = pdf_d1 / (spot * sigma * sqrt_t)
    vega = spot * pdf_d1 * sqrt_t / 100  # price change per 1 vol point (1.00 -> 0.01 sigma)

    if right == "call":
        delta = _norm_cdf(d1)
        theta_year = -(spot * pdf_d1 * sigma) / (2 * sqrt_t) - risk_free_rate * strike * discount * _norm_cdf(d2)
        rho = strike * years_to_expiry * discount * _norm_cdf(d2) / 100
    else:
        delta = _norm_cdf(d1) - 1
        theta_year = -(spot * pdf_d1 * sigma) / (2 * sqrt_t) + risk_free_rate * strike * discount * _norm_cdf(-d2)
        rho = -strike * years_to_expiry * discount * _norm_cdf(-d2) / 100

    return {
        "delta": delta,
        "gamma": gamma,
        "theta": theta_year / 365,  # convert to per-calendar-day decay
        "vega": vega,
        "rho": rho,
    }
