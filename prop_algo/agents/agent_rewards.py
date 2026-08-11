class AgentRewards:
    def __init__(self):
        self._total = 0
        self._history = []

    def record(self, value):
        self._total += value
        self._history.append(value)
        return self._total

    def summary(self):
        return {"total": self._total, "count": len(self._history)}


def compute_rewards(snapshot):
    return {
        "StrategyAgent": snapshot["learning"]["best_params"]["threshold"],
        "RiskAgent": snapshot["unified"]["stability"],
        "ExecutionAgent": 1.0 - snapshot["execution"]["slippage"],
        "GovernanceAgent": 1.0 if snapshot["global_mode"] == "NORMAL" else 0.5,
        "ResearchAgent": 1.0 if snapshot["learning"]["meta_mode"] == "NORMAL" else 0.7,
        "MarketAgent": snapshot["risk"]["liquidity"]["global_liquidity"]
    }
