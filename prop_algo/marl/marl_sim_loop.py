class MARLSimLoop:
    def __init__(self, controller, sim_env):
        self.controller = controller
        self.sim_env = sim_env

    def run(self, steps=1000):
        for _ in range(steps):
            # fake snapshot for observation (fields match MultiAgentEnv + rewards)
            snapshot = {
                "global_mode": "NORMAL",
                "learning": {
                    "best_params": {"threshold": 0.005},
                    "meta_mode": "NORMAL",
                },
                "unified": {"stability": 0.8, "coherence": 0.9},
                "risk": {"liquidity": {"global_liquidity": 1.0}, "anomalies": []},
                "execution": {"slippage": 0.001, "volatility": 0.001},
                "alerts": [],
            }

            result = self.controller.step(snapshot, {"StrategyAgent": 1, "RiskAgent": 1,
                                                     "ExecutionAgent": 1, "GovernanceAgent": 1,
                                                     "ResearchAgent": 1, "MarketAgent": 1})

            actions = {agent: {"action": result["actions"][agent]["action"]}
                       for agent in result["actions"]}

            combined, reward = self.sim_env.step(actions)

            # feed reward back into MARL controller
            self.controller.step(snapshot, reward)
