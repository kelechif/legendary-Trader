import numpy as np


class LiquiditySim:
    def __init__(self):
        self.global_liquidity = 1.0

    def step(self):
        self.global_liquidity = max(0.1, min(1.0, self.global_liquidity + np.random.normal(0, 0.05)))
        return {"global_liquidity": self.global_liquidity}
