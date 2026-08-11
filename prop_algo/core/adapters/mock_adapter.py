import random

import pandas as pd

from .base_adapter import BaseAdapter


class MockAdapter(BaseAdapter):
    def __init__(self, name):
        self.name = name
        self.balance = 10000
        self.symbols = ["EURUSD", "GBPUSD"]
        self._connected = False

    def connect(self):
        self._connected = True

    def close(self):
        self._connected = False

    def get_account_info(self):
        return {
            "name": self.name,
            "balance": self.balance,
            "equity": self.balance + random.uniform(-50, 50),
            "margin": random.uniform(100, 300),
        }

    def get_open_symbols(self):
        return self.symbols

    def get_history(self, symbol, lookback=500):
        prices = [1.0]
        for _ in range(lookback):
            prices.append(prices[-1] * (1 + random.uniform(-0.001, 0.001)))
        df = pd.DataFrame({"close": prices})
        return df

    def place_order(self, symbol, size, sl, tp):
        self.balance += random.uniform(-5, 5)
        return {"symbol": symbol, "size": size, "status": "FILLED", "sl": sl, "tp": tp}

    def place_limit_order(self, symbol, size, sl, tp, price):
        result = self.place_order(symbol, size, sl, tp)
        result["price"] = price
        result["order_type"] = "LIMIT"
        return result
