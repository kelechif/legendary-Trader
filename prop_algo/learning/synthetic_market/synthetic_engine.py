import numpy as np
import random

class SyntheticMarketEngine:
    def __init__(self, symbols):
        self.symbols = symbols

    def generate(self, length=2000):
        env = {}
        for sym in self.symbols:
            prices = [1.0]
            vols = []
            for _ in range(length):
                ret = random.gauss(0, 0.0005)
                prices.append(prices[-1] * (1 + ret))
                vols.append(abs(ret))

            env[sym] = {
                "prices": prices,
                "volatility": vols,
                "liquidity": [random.uniform(0.3, 1.0) for _ in range(length)],
                "news": [random.choice([0, 1]) for _ in range(length)],
            }

        corr = np.corrcoef([env[s]["prices"] for s in self.symbols])
        return env, corr
