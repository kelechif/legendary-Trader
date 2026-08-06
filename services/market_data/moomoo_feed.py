"""Moomoo OpenD daily kline loader with local parquet cache."""

import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from services.market_data import state
from services.market_data.indicators import compute_indicators, dataframe_to_candles
from services.shared.config import (
    ASSETS,
    DATA_DIR,
    MARKET_DATA_CFG,
    MOOMOO_HOST,
    MOOMOO_PORT,
    TRADING_CFG,
)
from services.shared import log_channels

_lock = threading.Lock()
_log = None
_loaded = False
_refresh_thread = None
_refresh_progress = {"total": 0, "done": 0, "running": False, "errors": 0}


def _log_info(msg, **fields):
    if _log:
        _log.info(msg)
    log_channels.log_event("data", "info", message=msg, **fields)


def _log_error(msg, **fields):
    if _log:
        _log.error(msg)
    log_channels.log_event("data", "error", message=msg, **fields)


def _kline_path(code: str) -> Path:
    safe = code.replace(".", "_")
    return DATA_DIR / "klines" / f"{safe}_1d.parquet"


def _fetch_history(code: str, start: str, end: str) -> pd.DataFrame:
    from moomoo import AuType, KLType, OpenQuoteContext

    retries = int(MARKET_DATA_CFG.get("fetch_retries", 3))
    delay = float(MARKET_DATA_CFG.get("fetch_retry_delay_sec", 1.5))
    last_err = None

    for attempt in range(retries):
        ctx = OpenQuoteContext(MOOMOO_HOST, MOOMOO_PORT)
        try:
            ret, data, _ = ctx.request_history_kline(
                code,
                start=start,
                end=end,
                ktype=KLType.K_DAY,
                autype=AuType.QFQ,
            )
        finally:
            ctx.close()

        if ret == 0 and data is not None and not data.empty:
            df = data.rename(columns={"time_key": "date"})
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            for col in ("open", "high", "low", "close", "volume"):
                df[col] = pd.to_numeric(df[col], errors="coerce")
            return df[["open", "high", "low", "close", "volume"]].dropna()

        last_err = ret
        if attempt < retries - 1:
            time.sleep(delay * (attempt + 1))

    raise RuntimeError(f"Moomoo kline request failed for {code} (ret={last_err})")


def load_or_fetch(code: str, years: int = 10, force_refresh: bool = False) -> pd.DataFrame:
    path = _kline_path(code)
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=365 * years)).strftime("%Y-%m-%d")

    if path.exists() and not force_refresh:
        df = pd.read_parquet(path)
        if not df.empty:
            last = pd.Timestamp(df.index.max())
            if last.date() >= (datetime.now() - timedelta(days=3)).date():
                return df

    _log_info(f"Fetching daily klines for {code}", ticker=code, start=start, end=end)
    try:
        df = _fetch_history(code, start, end)
    except RuntimeError:
        if path.exists():
            _log_info(f"Using stale cache for {code} after fetch failure", ticker=code)
            return pd.read_parquet(path)
        raise
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    log_channels.log_event("data", "kline_cached", ticker=code, bars=len(df))
    return df


def refresh_asset(code: str, indicator_params=None) -> list:
    years = int(MARKET_DATA_CFG.get("kline_years", 10))
    df = load_or_fetch(code, years=years)
    df = compute_indicators(df, indicator_params)
    candles = dataframe_to_candles(df)

    close = candles[-1]["close"] if candles else None
    closes = [c["close"] for c in candles if c.get("close") is not None]

    with state.lock:
        state.latest_price[code] = close
        state.price_history[code] = closes[-500:]
        if "1d" not in state.candle_history[code]:
            state.candle_history[code]["1d"] = []
        state.candle_history[code]["1d"] = candles[-300:]

    return candles


def refresh_all(indicator_params=None):
    global _loaded, _refresh_progress
    errors = []
    delay = float(MARKET_DATA_CFG.get("fetch_delay_sec", 0.35))
    _refresh_progress = {
        "total": len(ASSETS),
        "done": 0,
        "running": True,
        "errors": 0,
    }
    for i, code in enumerate(ASSETS):
        try:
            refresh_asset(code, indicator_params)
        except Exception as exc:
            errors.append((code, str(exc)))
            _refresh_progress["errors"] += 1
            _log_error(f"Failed to refresh {code}: {exc}", ticker=code)
        _refresh_progress["done"] = i + 1
        if delay and i < len(ASSETS) - 1:
            time.sleep(delay)

    _loaded = len(errors) < len(ASSETS)
    _refresh_progress["running"] = False
    if errors:
        log_channels.log_event(
            "data",
            "refresh_partial",
            failed=len(errors),
            total=len(ASSETS),
            errors=[{"ticker": c, "error": e} for c, e in errors[:5]],
        )
    else:
        log_channels.log_event("data", "refresh_complete", assets=len(ASSETS))
    return errors


def get_daily_candles(code: str) -> list:
    with state.lock:
        return list(state.candle_history.get(code, {}).get("1d", []))


def load_raw_kline_df(code: str):
    """Load OHLCV dataframe from parquet without indicators."""
    path = _kline_path(code)
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if df.index.name != "date" and "date" in df.columns:
        df = df.set_index("date")
    return df


def load_raw_kline_cache(tickers=None) -> dict:
    """Load raw OHLCV dataframes for WFO indicator recomputation."""
    tickers = tickers or ASSETS
    out = {}
    for code in tickers:
        df = load_raw_kline_df(code)
        if df is not None and not df.empty:
            out[code] = df
    return out


def load_cached_candles(code: str, indicator_params=None) -> list:
    """Load indicator-enriched candles from local parquet cache."""
    from services.market_data.indicators import compute_indicators, dataframe_to_candles

    df = load_raw_kline_df(code)
    if df is None or df.empty:
        return []
    df = compute_indicators(df, indicator_params)
    return dataframe_to_candles(df)


def start(logger=None, indicator_params=None, background=False):
    global _log, _refresh_thread
    _log = logger
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "klines").mkdir(parents=True, exist_ok=True)
    _log_info("Starting Moomoo daily data feed", host=MOOMOO_HOST, port=MOOMOO_PORT)

    if background:
        if _refresh_thread and _refresh_thread.is_alive():
            _log_info("Moomoo feed refresh already running")
            return
        _refresh_thread = threading.Thread(
            target=_refresh_worker,
            args=(indicator_params,),
            daemon=True,
            name="moomoo-feed",
        )
        _refresh_thread.start()
        _log_info("Moomoo kline refresh running in background", assets=len(ASSETS))
        return

    errors = refresh_all(indicator_params)
    if errors and TRADING_CFG.get("require_all_assets", False):
        raise RuntimeError(f"Moomoo feed failed for: {[c for c, _ in errors]}")


def is_ready():
    return _loaded


def feed_status() -> dict:
    with _lock:
        prog = dict(_refresh_progress)
    return {
        "provider": "moomoo",
        "ready": _loaded,
        "refresh_running": prog.get("running", False),
        "refresh_done": prog.get("done", 0),
        "refresh_total": prog.get("total", 0),
        "refresh_errors": prog.get("errors", 0),
    }


def _refresh_worker(indicator_params=None):
    try:
        errors = refresh_all(indicator_params)
        if errors and TRADING_CFG.get("require_all_assets", False):
            _log_error(
                "Moomoo feed partial failure with require_all_assets",
                failed=len(errors),
            )
    except Exception as exc:
        _log_error(f"Moomoo background refresh failed: {exc}")
