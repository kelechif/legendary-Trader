from .market_sim import MarketSim
from .liquidity_sim import LiquiditySim
from .vol_regime import VolRegimeSim
from .news_sim import NewsSim
from .interaction import InteractionEngine
from .reward_engine import RewardEngine


class SimulationEnv:
    def __init__(self):
        self.market = MarketSim()
        self.liquidity = LiquiditySim()
        self.vol = VolRegimeSim()
        self.news = NewsSim()
        self.interaction = InteractionEngine()
        self.rewards = RewardEngine()

    def step(self, actions):
        market_state = self.market.step()
        liquidity_state = self.liquidity.step()
        vol_state = self.vol.step()
        news_state = self.news.step()

        combined = {
            "price": market_state["price"],
            "volatility": vol_state["volatility"],
            "liquidity": liquidity_state["global_liquidity"],
            "anomalies": news_state["anomalies"]
        }

        combined = self.interaction.apply_actions(actions, combined)
        reward = self.rewards.compute(combined)

        return combined, reward
