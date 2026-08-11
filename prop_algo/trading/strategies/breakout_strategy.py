from .base_strategy import BaseStrategy


class BreakoutStrategy(BaseStrategy):
    def generate_signals(self, df):
        high = df["close"].rolling(100).max().iloc[-1]
        if df["close"].iloc[-1] > high:
            return {"signal": "BUY"}
        return {"signal": "HOLD"}
