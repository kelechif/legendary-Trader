"""MetaTrader 5 adapter (Windows host).

Requires a local MetaTrader 5 terminal and the MetaTrader5 Python package.
Do not run this inside Linux Docker containers — use BROKER_ADAPTER=mock there.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .base_adapter import BaseAdapter


class MT5Adapter(BaseAdapter):
    def __init__(
        self,
        login: int,
        password: str,
        server: str,
        path: str | None = None,
        name: str | None = None,
        symbols: list[str] | None = None,
    ):
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self.name = name or str(login)
        self.symbols = list(symbols or ["EURUSD", "GBPUSD"])
        self._connected = False

    @staticmethod
    def _mt5():
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError(
                "MT5Adapter requires the MetaTrader5 package on a Windows host "
                "with a local MetaTrader 5 terminal. "
                "Install: pip install MetaTrader5. "
                "Do not use MT5 inside Linux Docker; set BROKER_ADAPTER=mock in compose."
            ) from exc
        return mt5

    def connect(self):
        mt5 = self._mt5()
        init_kwargs: dict[str, Any] = {}
        if self.path:
            init_kwargs["path"] = self.path
        if not mt5.initialize(**init_kwargs):
            raise RuntimeError(
                f"MT5 initialize() failed: {mt5.last_error()}. "
                "Ensure MetaTrader 5 is installed and, if needed, set MT5_PATH "
                "to terminal64.exe. Linux Docker is not supported."
            )
        authorized = mt5.login(
            self.login, password=self.password, server=self.server
        )
        if not authorized:
            err = mt5.last_error()
            mt5.shutdown()
            raise RuntimeError(
                f"MT5 login failed for {self.login}@{self.server}: {err}. "
                "Check MT5_LOGIN / MT5_PASSWORD / MT5_SERVER."
            )
        self._connected = True

    def get_account_info(self):
        mt5 = self._mt5()
        info = mt5.account_info()
        if info is None:
            raise RuntimeError(
                f"MT5 account_info() failed: {mt5.last_error()}. "
                "Call connect() first and verify the terminal session."
            )
        return {
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "name": info.name or self.name,
        }

    def get_open_symbols(self):
        # Watchlist for market-data / strategy loops (matches MockAdapter usage).
        return list(self.symbols)

    def get_history(self, symbol, lookback=500):
        mt5 = self._mt5()
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, lookback)
        if rates is None or len(rates) == 0:
            raise RuntimeError(
                f"MT5 copy_rates_from_pos({symbol!r}) failed or returned empty: "
                f"{mt5.last_error()}. Check symbol name and MT5_SYMBOLS."
            )
        df = pd.DataFrame(rates)
        if "close" not in df.columns:
            raise RuntimeError(
                f"MT5 history for {symbol!r} missing 'close' column; got {list(df.columns)}."
            )
        return df

    def place_order(self, symbol, size, sl, tp):
        mt5 = self._mt5()
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(
                f"MT5 symbol_info_tick({symbol!r}) failed: {mt5.last_error()}."
            )
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(size),
            "type": mt5.ORDER_TYPE_BUY,
            "price": tick.ask,
            "sl": sl or 0.0,
            "tp": tp or 0.0,
            "deviation": 20,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is None:
            raise RuntimeError(
                f"MT5 order_send() returned None: {mt5.last_error()}."
            )
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(
                f"MT5 order rejected retcode={result.retcode} comment={result.comment!r}."
            )
        return {
            "symbol": symbol,
            "size": size,
            "status": "FILLED",
            "sl": sl,
            "tp": tp,
            "ticket": result.order,
            "price": result.price,
            "retcode": result.retcode,
            "broker": "mt5",
        }

    def place_limit_order(self, symbol, size, sl, tp, price):
        mt5 = self._mt5()
        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": float(size),
            "type": mt5.ORDER_TYPE_BUY_LIMIT,
            "price": float(price),
            "sl": sl or 0.0,
            "tp": tp or 0.0,
        }
        result = mt5.order_send(request)
        if result is None:
            raise RuntimeError(
                f"MT5 limit order_send() returned None: {mt5.last_error()}."
            )
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(
                f"MT5 limit order rejected retcode={result.retcode} "
                f"comment={result.comment!r}."
            )
        return {
            "symbol": symbol,
            "size": size,
            "status": "PENDING",
            "sl": sl,
            "tp": tp,
            "price": price,
            "order_type": "LIMIT",
            "ticket": result.order,
            "retcode": result.retcode,
            "broker": "mt5",
        }

    def close(self):
        if not self._connected:
            return
        mt5 = self._mt5()
        mt5.shutdown()
        self._connected = False
