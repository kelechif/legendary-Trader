class RewardEngine:
    def compute(self, market_state):
        return {
            "StrategyAgent": 1.0 - market_state["threshold"],
            "RiskAgent": market_state["liquidity"],
            "ExecutionAgent": 1.0 - market_state["slippage"],
            "GovernanceAgent": 1.0 if market_state["volatility"] < 0.003 else 0.5,
            "ResearchAgent": 1.0,
            "MarketAgent": market_state["liquidity"]
        }


class RewardLayer:
    """Reward layer — scores agent outcomes for learning / MARL feedback."""

    def __init__(self, engine=None):
        self.engine = engine or RewardEngine()
        self.state = {}

    def process(self, snapshot):
        rewards = snapshot.get("rewards", {}) if isinstance(snapshot, dict) else {}
        self.state = {"rewards": rewards}
        return self.state

    def run(self, snapshot):
        return self.process(snapshot)
