from __future__ import annotations

import pandas as pd

from trading_bot.logger import get_logger

logger = get_logger(__name__)


class DataFetcher:
    """Pulls OHLCV history for stocks and futures via Yahoo Finance.

    Futures tickers use Yahoo's continuous-contract convention (e.g. ES=F, CL=F, GC=F);
    stock/ETF tickers are plain symbols (e.g. AAPL, SPY). Both are handled identically.
    """

    def fetch(self, symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        import yfinance as yf

        logger.info("Fetching %s bars for %s (period=%s)", interval, symbol, period)
        df = yf.download(
            symbol, period=period, interval=interval, auto_adjust=True, progress=False
        )
        if df.empty:
            raise ValueError(f"No data returned for symbol {symbol!r}")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.rename(columns=str.lower)
        df.index.name = "date"
        return df[["open", "high", "low", "close", "volume"]].dropna()

    def fetch_many(
        self, symbols: list[str], period: str = "2y", interval: str = "1d"
    ) -> dict[str, pd.DataFrame]:
        result = {}
        for symbol in symbols:
            try:
                result[symbol] = self.fetch(symbol, period=period, interval=interval)
            except Exception as exc:  # noqa: BLE001 - keep pulling remaining symbols
                logger.warning("Skipping %s: %s", symbol, exc)
        return result
