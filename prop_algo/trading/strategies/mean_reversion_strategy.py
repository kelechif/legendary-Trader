from .base_strategy import BaseStrategy


class MeanReversionStrategy(BaseStrategy):
    def generate_signals(self, df):
        ma = df["close"].rolling(50).mean().iloc[-1]
        if df["close"].iloc[-1] < ma:
            return {"signal": "BUY"}
        return {"signal": "SELL"}
