import numpy as np


class VolRegimeSim:
    def __init__(self):
        self.regime = "NORMAL"

    def step(self):
        p = np.random.rand()
        if p < 0.05:
            self.regime = "CRISIS"
        elif p < 0.15:
            self.regime = "HIGH_VOL"
        else:
            self.regime = "NORMAL"

        vol_map = {
            "NORMAL": 0.001,
            "HIGH_VOL": 0.003,
            "CRISIS": 0.01
        }

        return {"regime": self.regime, "volatility": vol_map[self.regime]}
