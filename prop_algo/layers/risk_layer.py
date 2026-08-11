import numpy as np


class LiquiditySim:
    def __init__(self):
        self.global_liquidity = 1.0

    def step(self):
        self.global_liquidity = max(0.1, min(1.0, self.global_liquidity + np.random.normal(0, 0.05)))
        return {"global_liquidity": self.global_liquidity}


class RiskLayer:
    """Risk layer — constraints, budgets, and stability signals over market state."""

    def __init__(self, sim=None):
        self.sim = sim or LiquiditySim()
        self.state = {}

    def process(self, snapshot=None):
        if snapshot is None:
            self.state = self.sim.step()
        else:
            risk = snapshot.get("risk", {}) if isinstance(snapshot, dict) else {}
            self.state = {"risk": risk}
        return self.state

    def run(self, snapshot=None):
        return self.process(snapshot)
