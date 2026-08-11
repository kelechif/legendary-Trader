"""Intraday 5m bars from Moomoo OpenD for 0DTE regime loop."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from services.shared.config import MOOMOO_HOST, MOOMOO_PORT, OPTIONS_CFG


def _quote_ctx():
    from moomoo import OpenQuoteContext

    return OpenQuoteContext(MOOMOO_HOST, MOOMOO_PORT)


def _owner() -> str:
    return str(OPTIONS_CFG.get("moomoo", {}).get("underlying", "US.SPY"))


def _ktype():
    from moomoo import KLType

    tf = str(OPTIONS_CFG.get("moomoo", {}).get("loop", {}).get("timeframe", "5m"))
    mapping = {
        "1m": KLType.K_1M,
        "5m": KLType.K_5M,
        "15m": KLType.K_15M,
        "30m": KLType.K_30M,
        "60m": KLType.K_60M,
        "1h": KLType.K_60M,
    }
    return mapping.get(tf, KLType.K_5M)


def _time_hhmm(ts) -> int:
    if isinstance(ts, str):
        ts = pd.to_datetime(ts)
    if hasattr(ts, "hour"):
        return ts.hour * 100 + ts.minute
    return 0


def fetch_intraday_candles(
    code: str | None = None,
    *,
    days_back: int = 5,
    max_bars: int = 200,
) -> list[dict]:
    """Fetch recent intraday bars as strategy candle dicts."""
    from moomoo import AuType, RET_OK

    code = code or _owner()
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    ctx = _quote_ctx()
    try:
        ret, data, _ = ctx.request_history_kline(
            code,
            start=start,
            end=end,
            ktype=_ktype(),
            autype=AuType.QFQ,
        )
        if ret != RET_OK or data is None or data.empty:
            return []

        df = data.tail(max_bars).copy()
        time_col = "time_key" if "time_key" in df.columns else "time"
        candles = []
        for _, row in df.iterrows():
            ts = row[time_col]
            candles.append(
                {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0)),
                    "time_hhmm": _time_hhmm(ts),
                    "time_key": str(ts),
                }
            )
        return candles
    finally:
        ctx.close()


def attach_vix(candles: list[dict], vix_code: str | None = None) -> list[dict]:
    """Merge latest VIX proxy close onto each candle (snapshot-style)."""
    vix_code = vix_code or OPTIONS_CFG.get("moomoo", {}).get("loop", {}).get("vix_symbol")
    if not vix_code or not candles:
        return candles

    from moomoo import RET_OK

    ctx = _quote_ctx()
    try:
        ret, snap = ctx.get_market_snapshot([vix_code])
        if ret != RET_OK or snap is None or snap.empty:
            return candles
        vix = float(snap["last_price"].iloc[0])
    finally:
        ctx.close()

    out = []
    for c in candles:
        row = dict(c)
        row["vix"] = vix
        out.append(row)
    return out
