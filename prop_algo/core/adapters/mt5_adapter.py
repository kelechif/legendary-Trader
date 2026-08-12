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
            "login": info.login,
            "server": info.server,
            "trade_mode": int(info.trade_mode),
            "is_demo": info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO,
        }

    def require_demo(self):
        """Abort unless the connected account is a demo account."""
        info = self.get_account_info()
        if not info.get("is_demo"):
            raise RuntimeError(
                f"Refusing to trade: account {info.get('login')}@{info.get('server')} "
                f"is not DEMO (trade_mode={info.get('trade_mode')}). "
                "This host run is DEMO-only."
            )
        return info

    def get_positions(self, symbol: str | None = None):
        mt5 = self._mt5()
        positions = (
            mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        )
        if positions is None:
            raise RuntimeError(f"MT5 positions_get() failed: {mt5.last_error()}.")
        out = []
        for p in positions:
            side = "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL"
            out.append(
                {
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "side": side,
                    "volume": float(p.volume),
                    "price_open": float(p.price_open),
                    "profit": float(p.profit),
                }
            )
        return out

    def ensure_symbol(self, symbol: str):
        mt5 = self._mt5()
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(
                f"MT5 symbol_select({symbol!r}) failed: {mt5.last_error()}."
            )

    def _filling_type(self, symbol: str):
        """Pick an ORDER_FILLING_* mode supported by the symbol."""
        mt5 = self._mt5()
        info = mt5.symbol_info(symbol)
        if info is None:
            return mt5.ORDER_FILLING_RETURN
        mode = int(info.filling_mode)
        # MQL5: SYMBOL_FILLING_FOK=1, SYMBOL_FILLING_IOC=2 (not always on the Python module).
        fok_flag = getattr(mt5, "SYMBOL_FILLING_FOK", 1)
        ioc_flag = getattr(mt5, "SYMBOL_FILLING_IOC", 2)
        if mode & ioc_flag:
            return mt5.ORDER_FILLING_IOC
        if mode & fok_flag:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN

    def _filling_candidates(self, symbol: str) -> list[int]:
        """Preferred filling first, then remaining ORDER_FILLING_* modes."""
        mt5 = self._mt5()
        preferred = self._filling_type(symbol)
        rest = [
            mt5.ORDER_FILLING_RETURN,
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_FOK,
        ]
        out = [preferred]
        for mode in rest:
            if mode not in out:
                out.append(mode)
        return out

    def close_position(self, ticket: int):
        mt5 = self._mt5()
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            raise RuntimeError(
                f"MT5 close_position: ticket {ticket} not found: {mt5.last_error()}."
            )
        pos = positions[0]
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            raise RuntimeError(
                f"MT5 symbol_info_tick({pos.symbol!r}) failed: {mt5.last_error()}."
            )
        if pos.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        result = None
        last_err = None
        for filling in self._filling_candidates(pos.symbol):
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": float(pos.volume),
                "type": order_type,
                "position": int(ticket),
                "price": price,
                "deviation": 20,
                "type_filling": filling,
            }
            result = mt5.order_send(request)
            if result is None:
                last_err = f"order_send None: {mt5.last_error()}"
                continue
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                break
            last_err = f"retcode={result.retcode} comment={result.comment!r}"
            # 10030 = unsupported filling mode — try next candidate.
            if result.retcode != 10030:
                break
        if result is None:
            raise RuntimeError(f"MT5 close order_send() failed: {last_err}.")
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(
                f"MT5 close rejected retcode={result.retcode} comment={result.comment!r}."
            )
        return {
            "ticket": ticket,
            "symbol": pos.symbol,
            "status": "CLOSED",
            "deal": result.deal,
            "price": result.price,
            "retcode": result.retcode,
            "broker": "mt5",
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

    def place_order(self, symbol, size, sl, tp, side: str = "BUY"):
        mt5 = self._mt5()
        side_u = (side or "BUY").strip().upper()
        if side_u not in ("BUY", "SELL"):
            raise ValueError(f"side must be BUY or SELL, got {side!r}.")
        self.ensure_symbol(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(
                f"MT5 symbol_info_tick({symbol!r}) failed: {mt5.last_error()}."
            )
        if side_u == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        result = None
        last_err = None
        for filling in self._filling_candidates(symbol):
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(size),
                "type": order_type,
                "price": price,
                "sl": sl or 0.0,
                "tp": tp or 0.0,
                "deviation": 20,
                "type_filling": filling,
            }
            result = mt5.order_send(request)
            if result is None:
                last_err = f"order_send None: {mt5.last_error()}"
                continue
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                break
            last_err = f"retcode={result.retcode} comment={result.comment!r}"
            if result.retcode != 10030:
                break
            # Refresh price between filling-mode retries.
            tick = mt5.symbol_info_tick(symbol)
            if tick is not None:
                price = tick.ask if side_u == "BUY" else tick.bid
        if result is None:
            raise RuntimeError(f"MT5 order_send() failed: {last_err}.")
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(
                f"MT5 order rejected retcode={result.retcode} comment={result.comment!r}."
            )
        return {
            "symbol": symbol,
            "size": size,
            "side": side_u,
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
