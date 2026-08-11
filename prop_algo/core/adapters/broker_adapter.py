import requests
import pandas as pd

from .base_adapter import BaseAdapter

class BrokerAdapter(BaseAdapter):
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}"}

    def connect(self):
        pass

    def get_account_info(self):
        r = requests.get(f"{self.base_url}/account", headers=self._headers())
        return r.json()

    def get_open_symbols(self):
        r = requests.get(f"{self.base_url}/positions", headers=self._headers())
        return list(set([p["symbol"] for p in r.json()]))

    def get_history(self, symbol, lookback=500):
        r = requests.get(f"{self.base_url}/history/{symbol}?count={lookback}", headers=self._headers())
        df = pd.DataFrame(r.json())
        return df

    def place_order(self, symbol, size, sl, tp):
        payload = {"symbol": symbol, "size": size, "sl": sl, "tp": tp}
        r = requests.post(f"{self.base_url}/order", json=payload, headers=self._headers())
        return r.json()

    def place_limit_order(self, symbol, size, sl, tp, price):
        payload = {"symbol": symbol, "size": size, "sl": sl, "tp": tp, "price": price}
        r = requests.post(f"{self.base_url}/order/limit", json=payload, headers=self._headers())
        return r.json()

    def close(self):
        pass
