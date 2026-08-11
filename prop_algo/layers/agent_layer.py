class InteractionEngine:
    def __init__(self):
        pass

    def apply_actions(self, actions, market_state):
        # Example: ExecutionAgent action affects slippage
        if actions["ExecutionAgent"]["action"] == 1:  # SWITCH_TO_LIMIT
            market_state["slippage"] = market_state["volatility"] * 0.5
        else:
            market_state["slippage"] = market_state["volatility"] * 1.2

        # StrategyAgent action affects threshold
        if actions["StrategyAgent"]["action"] == 1:  # EVOLVE_STRATEGIES
            market_state["threshold"] = 0.002
        else:
            market_state["threshold"] = 0.005

        return market_state


class AgentLayer:
    """Agent layer — multi-agent decisions over risk-filtered market context."""

    def __init__(self, engine=None):
        self.engine = engine or InteractionEngine()
        self.state = {}

    def process(self, snapshot):
        agents = snapshot.get("agents", {}) if isinstance(snapshot, dict) else {}
        self.state = {"agents": agents}
        return self.state

    def run(self, snapshot):
        return self.process(snapshot)
