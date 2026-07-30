from __future__ import annotations

import numpy as np
import pandas as pd


def make_synthetic_ohlcv(n: int = 600, seed: int = 7, start_price: float = 100.0) -> pd.DataFrame:
    """Deterministic random-walk OHLCV data for tests (no network access)."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.0003, scale=0.012, size=n)
    close = start_price * np.cumprod(1 + returns)

    high = close * (1 + np.abs(rng.normal(0, 0.004, size=n)))
    low = close * (1 - np.abs(rng.normal(0, 0.004, size=n)))
    open_ = low + (high - low) * rng.uniform(0, 1, size=n)
    volume = rng.integers(1_000_000, 5_000_000, size=n)

    dates = pd.bdate_range("2022-01-03", periods=n)
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=dates
    )
    df.index.name = "date"
    return df
