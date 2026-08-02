"""Technical indicators implemented directly on pandas Series/DataFrames.

No external TA library dependency is required.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(
    series: pd.Series, window: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(series, window)
    std = series.rolling(window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / window, adjust=False).mean()


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff().fillna(0))
    return (direction * df["volume"]).cumsum()


def rolling_volatility(series: pd.Series, window: int = 20) -> pd.Series:
    return series.pct_change().rolling(window).std()


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with a standard set of indicator columns added."""
    out = df.copy()
    close = out["close"]

    out["sma_20"] = sma(close, 20)
    out["sma_50"] = sma(close, 50)
    out["sma_200"] = sma(close, 200)
    out["ema_12"] = ema(close, 12)
    out["ema_26"] = ema(close, 26)
    out["rsi_14"] = rsi(close, 14)

    macd_line, signal_line, hist = macd(close)
    out["macd"] = macd_line
    out["macd_signal"] = signal_line
    out["macd_hist"] = hist

    bb_upper, bb_mid, bb_lower = bollinger_bands(close)
    out["bb_upper"] = bb_upper
    out["bb_mid"] = bb_mid
    out["bb_lower"] = bb_lower
    band_width = (bb_upper - bb_lower).replace(0, np.nan)
    out["bb_pct_b"] = (close - bb_lower) / band_width

    out["atr_14"] = atr(out, 14)
    out["atr_pct"] = out["atr_14"] / close
    out["obv"] = obv(out)
    out["volatility_20"] = rolling_volatility(close, 20)
    out["return_1"] = close.pct_change(1)

    return out


def build_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Build the model-ready feature set from an indicator-enriched DataFrame."""
    feat = pd.DataFrame(index=df.index)

    feat["ret_1"] = df["close"].pct_change(1)
    feat["ret_3"] = df["close"].pct_change(3)
    feat["ret_5"] = df["close"].pct_change(5)
    feat["ret_10"] = df["close"].pct_change(10)

    feat["sma20_ratio"] = df["close"] / df["sma_20"] - 1
    feat["sma50_ratio"] = df["close"] / df["sma_50"] - 1
    feat["sma200_ratio"] = df["close"] / df["sma_200"] - 1
    feat["sma_trend"] = df["sma_20"] / df["sma_50"] - 1

    feat["rsi_14"] = df["rsi_14"]
    feat["macd_hist"] = df["macd_hist"]
    feat["bb_pct_b"] = df["bb_pct_b"]
    feat["atr_pct"] = df["atr_pct"]
    feat["volatility_20"] = df["volatility_20"]

    volume_change = df["volume"].pct_change(5)
    feat["volume_change_5"] = volume_change.replace([np.inf, -np.inf], np.nan)

    return feat
