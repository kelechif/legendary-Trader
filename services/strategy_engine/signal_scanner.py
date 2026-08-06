"""Scan the universe for signals and rank entry candidates."""

from services.market_data.moomoo_feed import get_daily_candles
from services.shared.config import ASSETS, TRADING_CFG
from services.strategy_engine import choose_signal
from services.strategy_engine.plugins.institutional_trend import _regime_ok, _valid
from services.strategy_engine.regime import classify_regime, entry_allowed


def _regime_cfg():
    return TRADING_CFG.get("regime", {})


def trend_score(candle: dict, params: dict) -> float:
    """Higher = stronger trend setup (MA stack + RSI health + volume)."""
    if not _regime_ok(candle, params):
        return -1.0

    close = candle.get("close") or 1.0
    stack = 0.0
    if _valid(candle, "ema10", "ema20", "sma50"):
        stack += (candle["ema10"] - candle["ema20"]) / close
        stack += (candle["ema20"] - candle["sma50"]) / close
        stack += (candle["sma50"] - candle.get("sma200", candle["sma50"])) / close

    rsi = candle.get("rsi14")
    rsi_health = 1.0 - abs(rsi - 50) / 50 if rsi is not None else 0.0

    vol = candle.get("volume") or 0
    vol_base = candle.get("vol_sma20") or 1
    vol_ratio = min(vol / vol_base, 3.0) / 3.0 if vol_base else 0.0

    macd = max(candle.get("macd_hist") or 0, 0) / close * 100
    return stack * 1000 + rsi_health * 2 + vol_ratio + macd


def scan_asset(asset: str, strategy: str, params: dict) -> dict | None:
    candles = get_daily_candles(asset)
    if len(candles) < 2:
        return None

    for c in candles:
        c["ticker"] = asset

    current = candles[-1]
    regime_label = classify_regime(current, params)
    signal = choose_signal(strategy, [], params, candles)
    score = trend_score(current, params)

    if signal == "BUY" and not entry_allowed(regime_label, _regime_cfg()):
        signal = "HOLD"

    return {
        "asset": asset,
        "signal": signal,
        "score": round(score, 4),
        "regime": _regime_ok(current, params),
        "regime_label": regime_label,
        "close": current.get("close"),
        "date": current.get("date"),
        "rsi14": current.get("rsi14"),
    }


def scan_universe(strategy: str, params: dict, assets=None) -> list:
    assets = assets or ASSETS
    results = []
    for asset in assets:
        row = scan_asset(asset, strategy, params)
        if row:
            results.append(row)
    return results


def rank_entry_candidates(scanned: list) -> list:
    buys = [r for r in scanned if r["signal"] == "BUY"]
    buys.sort(key=lambda r: r["score"], reverse=True)
    return buys


def summarize_scan(scanned: list) -> dict:
    return {
        "total": len(scanned),
        "buy": sum(1 for r in scanned if r["signal"] == "BUY"),
        "sell": sum(1 for r in scanned if r["signal"] == "SELL"),
        "hold": sum(1 for r in scanned if r["signal"] == "HOLD"),
        "in_regime": sum(1 for r in scanned if r.get("regime")),
        "bull": sum(1 for r in scanned if r.get("regime_label") == "BULL"),
        "bear": sum(1 for r in scanned if r.get("regime_label") == "BEAR"),
        "sideways": sum(1 for r in scanned if r.get("regime_label") == "SIDEWAYS"),
    }
