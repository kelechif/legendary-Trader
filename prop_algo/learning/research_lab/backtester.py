import numpy as np
import pandas as pd


class Backtester:
    def __init__(self, df, params):
        self.df = df
        self.params = params

    def run(self):
        lookback = self.params["lookback"]
        threshold = self.params["threshold"]

        # Positional indexing (walkforward segments retain original index labels).
        closes = self.df["close"].reset_index(drop=True)
        returns = closes.pct_change().fillna(0)

        signals = []
        for i in range(len(closes)):
            if i < lookback:
                signals.append(0)
                continue
            window = closes[i-lookback:i]
            mean = window.mean()
            dev = closes[i] - mean

            if dev > threshold:
                signals.append(-1)  # mean reversion short
            elif dev < -threshold:
                signals.append(1)   # mean reversion long
            else:
                signals.append(0)

        signals = np.array(signals)
        pnl = signals * returns.values

        return pd.Series(pnl)
