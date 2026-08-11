"""Market layer — thin wrappers; sims live in prop_algo.simulation."""

from simulation.market_sim import MarketSim
from simulation.vol_regime import VolRegimeSim
from simulation.news_sim import NewsSim

__all__ = ["MarketSim", "VolRegimeSim", "NewsSim", "MarketLayer"]


class MarketLayer:
    """Market layer — synthetic / live market state feeding the stack."""

    def __init__(self, sim=None):
        self.sim = sim or MarketSim()
        self.state = {}

    def process(self, snapshot=None):
        if snapshot is None:
            self.state = self.sim.step()
        else:
            market = snapshot.get("market", {}) if isinstance(snapshot, dict) else {}
            self.state = {"market": market}
        return self.state

    def run(self, snapshot=None):
        return self.process(snapshot)
