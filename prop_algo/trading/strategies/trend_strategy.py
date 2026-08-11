from .base_strategy import BaseStrategy


class TrendStrategy(BaseStrategy):
    def generate_signals(self, df):
        if df["close"].iloc[-1] > df["close"].iloc[-50]:
            return {"signal": "BUY"}
        return {"signal": "SELL"}
