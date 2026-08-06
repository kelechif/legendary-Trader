"""Moomoo OpenD 0DTE option chain via OpenQuoteContext."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from services.shared.config import MOOMOO_HOST, MOOMOO_PORT, OPTIONS_CFG


def _quote_ctx():
    from moomoo import OpenQuoteContext

    return OpenQuoteContext(MOOMOO_HOST, MOOMOO_PORT)


def _owner_code() -> str:
    mm = OPTIONS_CFG.get("moomoo", {})
    return str(mm.get("underlying", "US.SPY"))


def get_zero_dte_chain_info(owner: str | None = None) -> dict | None:
    """Return chain_info dict for today's 0DTE from zero_dte screener."""
    from moomoo import OptionMarket, RET_OK

    owner = owner or _owner_code()
    market_key = str(OPTIONS_CFG.get("moomoo", {}).get("option_market", "US_SECURITY"))
    ctx = _quote_ctx()
    try:
        option_market = getattr(OptionMarket, market_key, OptionMarket.US_SECURITY)
        ret, data = ctx.get_option_zero_dte_screener(market=option_market, count=500)
        if ret != RET_OK or not data:
            return None
        items = data.get("item_list")
        if items is None or (hasattr(items, "empty") and items.empty):
            return None
        df = items if isinstance(items, pd.DataFrame) else pd.DataFrame(items)
        if df.empty:
            return None
        owner_col = "owner" if "owner" in df.columns else "code"
        row = df[df[owner_col] == owner]
        if row.empty:
            row = df.iloc[[0]]
        r = row.iloc[0]
        chain_info = r.get("chain_info")
        if isinstance(chain_info, str):
            import json

            chain_info = json.loads(chain_info)
        if not isinstance(chain_info, dict):
            chain_info = {
                k: r[k]
                for k in (
                    "strike_date_timestamp",
                    "product_code",
                    "multiplier",
                    "contract_share_size",
                    "expiration_type",
                    "underlying",
                )
                if k in r.index and pd.notna(r[k])
            }
        if "underlying" not in chain_info:
            chain_info["underlying"] = owner
        return chain_info
    finally:
        ctx.close()


def get_zero_dte_contracts(owner: str | None = None, chain_info: dict | None = None) -> pd.DataFrame:
    """Fetch 0DTE contracts with Greeks for owner."""
    from moomoo import RET_OK

    owner = owner or _owner_code()
    chain_info = chain_info or get_zero_dte_chain_info(owner)
    if not chain_info:
        return pd.DataFrame()

    ctx = _quote_ctx()
    try:
        ret, data = ctx.get_option_zero_dte_contract(
            owner=owner,
            strike_date_timestamp=int(chain_info["strike_date_timestamp"]),
            chain_info=chain_info,
        )
        if ret != RET_OK or data is None or (hasattr(data, "empty") and data.empty):
            return pd.DataFrame()
        return data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    finally:
        ctx.close()


def get_chain_for_backtest_date(
    owner: str | None = None,
    iso_date: str | None = None,
    *,
    use_live_today: bool = True,
) -> tuple[pd.DataFrame, str]:
    """
    Option chain for backtest date.
    Today + use_live_today: prefer live 0DTE contract chain (bid/ask/Greeks).
    """
    owner = owner or _owner_code()
    if not iso_date:
        iso_date = date.today().isoformat()

    if use_live_today and iso_date == date.today().isoformat():
        live = get_zero_dte_contracts(owner)
        if live is not None and not live.empty:
            return live, "live_0dte"
        chain = get_option_chain_for_date(owner, iso_date)
        if chain is not None and not chain.empty:
            return chain, "chain_today"
        return pd.DataFrame(), "none"

    chain = get_option_chain_for_date(owner, iso_date)
    if chain is not None and not chain.empty:
        return chain, "chain_historical"
    return pd.DataFrame(), "none"


def get_option_chain_for_date(owner: str | None = None, iso_date: str | None = None) -> pd.DataFrame:
    """Fetch option chain for a single expiry date (yyyy-mm-dd)."""
    from moomoo import RET_OK

    owner = owner or _owner_code()
    if not iso_date:
        iso_date = date.today().isoformat()
    ctx = _quote_ctx()
    try:
        ret, data = ctx.get_option_chain(owner, start=iso_date, end=iso_date)
        if ret != RET_OK or data is None or data.empty:
            return pd.DataFrame()
        return data
    finally:
        ctx.close()


def _row_by_code(df: pd.DataFrame, code: str) -> pd.Series | None:
    code_col = "code" if "code" in df.columns else "option_code"
    if code_col not in df.columns:
        return None
    match = df[df[code_col].astype(str) == str(code)]
    if match.empty:
        return None
    return match.iloc[0]


def _price(row: pd.Series, *names: str) -> float | None:
    for n in names:
        if n in row.index and pd.notna(row[n]):
            try:
                v = float(row[n])
                if v > 0:
                    return v
            except (TypeError, ValueError):
                pass
    return None


def credit_for_vertical(
    chain_df: pd.DataFrame | None,
    short_leg: dict,
    long_leg: dict,
    *,
    width: float = 5.0,
    short_delta: float = 0.12,
) -> tuple[float, str]:
    """
    Net credit for short vertical (sell short, buy long).
    Returns (credit_per_share, source).
    """
    if chain_df is not None and not chain_df.empty and short_leg.get("code"):
        sr = _row_by_code(chain_df, short_leg["code"])
        lr = _row_by_code(chain_df, long_leg["code"])
        if sr is not None and lr is not None:
            bid_short = _price(sr, "bid_price", "bid", "last_price")
            ask_long = _price(lr, "ask_price", "ask", "last_price")
            if bid_short is not None and ask_long is not None:
                credit = max(0.05, bid_short - ask_long)
                return round(min(credit, width - 0.05), 2), "chain_bid_ask"
            last_s = _price(sr, "last_price", "nominal_price")
            last_l = _price(lr, "last_price", "nominal_price")
            if last_s is not None and last_l is not None:
                credit = max(0.05, last_s - last_l)
                return round(min(credit, width - 0.05), 2), "chain_last"

    # 0DTE OTM credit estimate: ~15–25% of width at 0.12 delta
    pct = 0.18 + short_delta * 0.3
    credit = max(0.08, min(width * pct, width - 0.10))
    return round(credit, 2), "estimate"


def get_option_chain_today(owner: str | None = None) -> pd.DataFrame:
    """Fallback: standard option chain for today's expiry."""
    from moomoo import RET_OK

    owner = owner or _owner_code()
    today = date.today().isoformat()
    ctx = _quote_ctx()
    try:
        ret, data = ctx.get_option_chain(owner, start=today, end=today)
        if ret != RET_OK or data is None or data.empty:
            return pd.DataFrame()
        return data
    finally:
        ctx.close()


def pick_contracts_for_vertical(
    contracts: pd.DataFrame,
    direction: str,
    *,
    short_delta: float = 0.12,
    width: float = 5.0,
) -> tuple[dict, dict] | None:
    """
    Pick short + long leg for a credit vertical from 0DTE chain.
    direction: bullish (put spread) | bearish (call spread)
    """
    if contracts is None or contracts.empty:
        return None

    direction = direction.lower()
    opt_col = "option_type" if "option_type" in contracts.columns else "type"
    delta_col = next((c for c in contracts.columns if "delta" in c.lower()), None)
    strike_col = next((c for c in contracts.columns if "strike" in c.lower()), "strike_price")
    code_col = "code" if "code" in contracts.columns else "option_code"

    df = contracts.copy()
    if opt_col in df.columns:
        if direction in ("bull", "bullish", "long", "1", "buy"):
            df = df[df[opt_col].astype(str).str.upper().str.contains("PUT", na=False)]
            target_sign = -1
        else:
            df = df[df[opt_col].astype(str).str.upper().str.contains("CALL", na=False)]
            target_sign = 1
    else:
        target_sign = -1 if direction in ("bull", "bullish", "long", "1", "buy") else 1

    if df.empty:
        return None

    if delta_col:
        df["_abs_delta"] = (df[delta_col].astype(float) - target_sign * short_delta).abs()
        short_row = df.sort_values("_abs_delta").iloc[0]
    else:
        short_row = df.iloc[len(df) // 3]

    short_strike = float(short_row[strike_col])
    if target_sign < 0:
        long_strike = short_strike - width
        long_candidates = df[df[strike_col].astype(float) <= long_strike + 0.01]
    else:
        long_strike = short_strike + width
        long_candidates = df[df[strike_col].astype(float) >= long_strike - 0.01]

    if long_candidates.empty:
        return None
    long_row = long_candidates.iloc[(long_candidates[strike_col].astype(float) - long_strike).abs().argmin()]

    short_leg = {"code": str(short_row[code_col]), "strike": short_strike}
    long_leg = {"code": str(long_row[code_col]), "strike": float(long_row[strike_col])}
    return short_leg, long_leg
