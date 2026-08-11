import numpy as np
import random


class MarketSim:
    def __init__(self):
        self.price = 1.0
        self.volatility = 0.001
        self.liquidity = 1.0

    def step(self):
        ret = np.random.normal(0, self.volatility)
        self.price *= (1 + ret)

        # liquidity fluctuates
        self.liquidity = max(0.1, min(1.0, self.liquidity + random.uniform(-0.05, 0.05)))

        return {
            "price": self.price,
            "volatility": self.volatility,
            "liquidity": self.liquidity
        }
