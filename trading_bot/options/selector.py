from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from trading_bot.options.chain import mid_price
from trading_bot.options.pricing import bs_greeks


@dataclass
class SelectedContract:
    contract_symbol: str
    strike: float
    expiration: str
    dte_days: int
    right: str
    premium: float
    implied_vol: float
    delta: float


class ContractSelector:
    """Picks the chain contract whose delta is closest to a target, using each
    contract's own implied volatility (as quoted) to compute Black-Scholes delta.
    """

    def __init__(self, risk_free_rate: float = 0.04):
        self.risk_free_rate = risk_free_rate

    def select(self, chain_df: pd.DataFrame, underlying_price: float, expiration: str,
               right: str, target_delta: float) -> SelectedContract:
        today = datetime.now(timezone.utc).date()
        dte_days = (datetime.strptime(expiration, "%Y-%m-%d").date() - today).days
        years = max(dte_days, 1) / 365

        df = chain_df.copy()
        df["_iv"] = df["impliedVolatility"].fillna(0)
        df = df[df["_iv"] > 0]
        if df.empty:
            raise ValueError("No contracts with usable implied volatility to compute delta.")

        df["_delta"] = df.apply(
            lambda r: bs_greeks(underlying_price, r["strike"], years, self.risk_free_rate, r["_iv"], right)["delta"],
            axis=1,
        )
        target = target_delta if right == "call" else -abs(target_delta)
        df["_delta_diff"] = (df["_delta"] - target).abs()
        best = df.sort_values("_delta_diff").iloc[0]

        return SelectedContract(
            contract_symbol=best["contractSymbol"],
            strike=float(best["strike"]),
            expiration=expiration,
            dte_days=dte_days,
            right=right,
            premium=mid_price(best),
            implied_vol=float(best["_iv"]),
            delta=float(best["_delta"]),
        )
