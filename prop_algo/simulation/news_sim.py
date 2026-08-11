import numpy as np


class NewsSim:
    def __init__(self):
        self.anomalies = []

    def step(self):
        if np.random.rand() < 0.1:
            self.anomalies.append("NEWS_SHOCK")

        return {"anomalies": self.anomalies[-5:]}
