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
