"""Daily OHLCV indicator computation for equity trend strategies."""

import pandas as pd


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length, min_periods=length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(length, min_periods=length).mean()
    avg_loss = loss.rolling(length, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(length, min_periods=length).mean()


def compute_indicators(df: pd.DataFrame, params=None) -> pd.DataFrame:
    """Add SMA/EMA/MACD/RSI/ATR columns to a daily OHLCV dataframe."""
    params = params or {}
    ema_fast = int(params.get("ema_fast", 10))
    ema_slow = int(params.get("ema_slow", 20))
    rsi_len = int(params.get("rsi_len", 14))
    atr_len = int(params.get("atr_len", 14))
    macd_fast = int(params.get("macd_fast", 12))
    macd_slow = int(params.get("macd_slow", 26))
    macd_signal = int(params.get("macd_signal", 9))

    out = df.copy()
    out["sma200"] = sma(out["close"], 200)
    out["sma50"] = sma(out["close"], 50)
    out["ema10"] = ema(out["close"], 10)
    out["ema20"] = ema(out["close"], 20)
    out[f"ema{ema_fast}"] = ema(out["close"], ema_fast)
    out[f"ema{ema_slow}"] = ema(out["close"], ema_slow)
    macd_line, signal_line, hist = macd(
        out["close"], macd_fast, macd_slow, macd_signal
    )
    out["macd_line"] = macd_line
    out["macd_signal"] = signal_line
    out["macd_hist"] = hist
    out["rsi14"] = rsi(out["close"], rsi_len)
    out["atr14"] = atr(out, atr_len)
    out["vol_sma20"] = out["volume"].rolling(20, min_periods=20).mean()
    out["ema_fast"] = out[f"ema{ema_fast}"]
    out["ema_slow"] = out[f"ema{ema_slow}"]
    return out


def row_to_candle(row) -> dict:
    """Convert a dataframe row (with indicators) to a strategy candle dict."""
    def _f(key):
        val = row[key]
        if pd.isna(val):
            return None
        return float(val)

    candle = {
        "date": str(row.name) if row.name is not None else None,
        "open": _f("open"),
        "high": _f("high"),
        "low": _f("low"),
        "close": _f("close"),
        "volume": _f("volume"),
        "sma200": _f("sma200"),
        "sma50": _f("sma50"),
        "ema10": _f("ema10") if "ema10" in row.index else _f("ema_fast"),
        "ema20": _f("ema20") if "ema20" in row.index else _f("ema_slow"),
        "ema_fast": _f("ema_fast"),
        "ema_slow": _f("ema_slow"),
        "macd_line": _f("macd_line"),
        "macd_signal": _f("macd_signal"),
        "macd_hist": _f("macd_hist"),
        "rsi14": _f("rsi14"),
        "atr14": _f("atr14"),
        "vol_sma20": _f("vol_sma20"),
    }
    return candle


def dataframe_to_candles(df: pd.DataFrame) -> list:
    return [row_to_candle(row) for _, row in df.iterrows()]
