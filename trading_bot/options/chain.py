from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from trading_bot.logger import get_logger

logger = get_logger(__name__)


class OptionsChainFetcher:
    """Live option-chain snapshots via Yahoo Finance. Only current quotes are
    available (no historical chain data), so this is used for live/paper
    trading and manual exploration, not for historical backtesting.
    """

    def list_expirations(self, symbol: str) -> list[str]:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        expirations = list(ticker.options)
        if not expirations:
            raise ValueError(f"No listed options found for {symbol!r}")
        return expirations

    def fetch_chain(self, symbol: str, expiration: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        import yfinance as yf

        logger.info("Fetching option chain for %s @ %s", symbol, expiration)
        ticker = yf.Ticker(symbol)
        chain = ticker.option_chain(expiration)
        return chain.calls, chain.puts

    def nearest_expiration(self, symbol: str, target_dte_days: int) -> str:
        expirations = self.list_expirations(symbol)
        today = datetime.now(timezone.utc).date()

        def dte(exp_str: str) -> int:
            return (datetime.strptime(exp_str, "%Y-%m-%d").date() - today).days

        candidates = [(abs(dte(e) - target_dte_days), e) for e in expirations if dte(e) > 0]
        if not candidates:
            raise ValueError(f"No future expirations available for {symbol!r}")
        candidates.sort(key=lambda pair: pair[0])
        return candidates[0][1]

    def quote_contract(self, symbol: str, expiration: str, contract_symbol: str, right: str) -> float:
        """Re-quote a specific contract's current mid price (used to close a position)."""
        calls, puts = self.fetch_chain(symbol, expiration)
        df = calls if right == "call" else puts
        row = df[df["contractSymbol"] == contract_symbol]
        if row.empty:
            raise ValueError(f"Contract {contract_symbol!r} not found in current chain")
        return mid_price(row.iloc[0])


def mid_price(row: pd.Series) -> float:
    bid, ask = float(row.get("bid", 0) or 0), float(row.get("ask", 0) or 0)
    if bid > 0 and ask > 0:
        return round((bid + ask) / 2, 4)
    return float(row.get("lastPrice", 0) or 0)
