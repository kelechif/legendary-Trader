"""cTrader Open API-style REST/WS adapter.

Expects a reachable gateway at CTRADER_BASE_URL with bearer auth.
Does not invent fills when the remote API fails — errors are raised.
"""

from __future__ import annotations

import pandas as pd
import requests

from .base_adapter import BaseAdapter


class CTraderAdapter(BaseAdapter):
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: str,
        base_url: str,
        name: str | None = None,
        symbols: list[str] | None = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.name = name or "ctrader"
        self.symbols = list(symbols or ["EURUSD", "GBPUSD"])
        self.ws = None
        self._connected = False

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(
                method, url, headers=self._headers(), timeout=30, **kwargs
            )
        except requests.RequestException as exc:
            raise RuntimeError(
                f"CTraderAdapter {method} {url} failed: {exc}. "
                "Check CTRADER_BASE_URL / network, or use BROKER_ADAPTER=mock."
            ) from exc
        if response.status_code >= 400:
            raise RuntimeError(
                f"CTraderAdapter {method} {url} -> HTTP {response.status_code}: "
                f"{response.text[:500]!r}. Check CTRADER_ACCESS_TOKEN and gateway."
            )
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"CTraderAdapter {method} {url} returned non-JSON body."
            ) from exc

    def connect(self):
        if not self.access_token or not self.base_url:
            raise RuntimeError(
                "CTraderAdapter missing access_token or base_url. "
                "Set CTRADER_ACCESS_TOKEN and CTRADER_BASE_URL."
            )
        # Validate credentials with a lightweight account probe.
        self._request("GET", "/accounts")

        try:
            import websocket
        except ImportError as exc:
            raise RuntimeError(
                "CTraderAdapter streaming requires websocket-client. "
                "Install: pip install websocket-client."
            ) from exc

        try:
            self.ws = websocket.WebSocket()
            self.ws.connect(
                f"{self.base_url}/stream?access_token={self.access_token}",
                timeout=15,
            )
        except Exception as exc:
            raise RuntimeError(
                f"CTraderAdapter WebSocket connect failed: {exc}. "
                "REST may still work if /accounts succeeded; fix stream URL/token "
                "or point CTRADER_BASE_URL at a reachable gateway."
            ) from exc
        self._connected = True

    def get_account_info(self):
        data = self._request("GET", "/accounts")
        if not isinstance(data, list) or not data:
            raise RuntimeError(
                "CTraderAdapter /accounts returned no accounts. "
                "Check CTRADER_CLIENT_ID / token scopes."
            )
        row = data[0]
        try:
            return {
                "balance": row["balance"],
                "equity": row["equity"],
                "margin": row["margin"],
                "name": row.get("accountId", self.name),
            }
        except KeyError as exc:
            raise RuntimeError(
                f"CTraderAdapter /accounts missing field {exc}. Got keys: {list(row)}."
            ) from exc

    def get_open_symbols(self):
        return list(self.symbols)

    def get_history(self, symbol, lookback=500):
        data = self._request(
            "GET", f"/history/{symbol}?period=M1&count={lookback}"
        )
        df = pd.DataFrame(data)
        if df.empty or "close" not in df.columns:
            raise RuntimeError(
                f"CTraderAdapter history for {symbol!r} empty or missing 'close'. "
                f"columns={list(df.columns)}."
            )
        return df

    def place_order(self, symbol, size, sl, tp):
        payload = {
            "symbol": symbol,
            "volume": size,
            "type": "BUY",
            "sl": sl,
            "tp": tp,
        }
        data = self._request("POST", "/orders", json=payload)
        if not isinstance(data, dict):
            raise RuntimeError(
                f"CTraderAdapter /orders returned unexpected payload: {data!r}."
            )
        data.setdefault("broker", "ctrader")
        return data

    def place_limit_order(self, symbol, size, sl, tp, price):
        payload = {
            "symbol": symbol,
            "volume": size,
            "type": "BUY_LIMIT",
            "price": price,
            "sl": sl,
            "tp": tp,
        }
        data = self._request("POST", "/orders", json=payload)
        if not isinstance(data, dict):
            raise RuntimeError(
                f"CTraderAdapter limit /orders returned unexpected payload: {data!r}."
            )
        data.setdefault("order_type", "LIMIT")
        data.setdefault("broker", "ctrader")
        return data

    def close(self):
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        self._connected = False
