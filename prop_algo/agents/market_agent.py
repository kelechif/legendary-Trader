from .base_agent import BaseAgent


class MarketAgent(BaseAgent):
    def observe(self, snapshot):
        self.state["liquidity"] = snapshot["risk"]["liquidity"]["global_liquidity"]

    def act(self):
        if self.state["liquidity"] < 0.5:
            return {"intent": "MARKET_STRESS"}
        return {"intent": "MARKET_NORMAL"}
