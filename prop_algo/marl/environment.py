class MultiAgentEnv:
    def __init__(self):
        pass

    def get_observation(self, snapshot, agent_name):
        # compress snapshot into agent-specific observation vector
        obs = []

        if agent_name == "StrategyAgent":
            obs = [
                snapshot["learning"]["best_params"]["threshold"],
                snapshot["unified"]["stability"],
                snapshot["risk"]["liquidity"]["global_liquidity"]
            ]

        elif agent_name == "RiskAgent":
            obs = [
                snapshot["unified"]["stability"],
                len(snapshot["risk"]["anomalies"]),
                snapshot["risk"]["liquidity"]["global_liquidity"]
            ]

        elif agent_name == "ExecutionAgent":
            obs = [
                snapshot["execution"]["slippage"],
                snapshot["execution"]["volatility"],
                snapshot["risk"]["liquidity"]["global_liquidity"]
            ]

        # etc for other agents...
        elif agent_name == "GovernanceAgent":
            obs = [
                len(snapshot.get("alerts") or []),
                1.0 if snapshot.get("global_mode") == "NORMAL" else 0.5,
            ]

        elif agent_name == "ResearchAgent":
            learning = snapshot.get("learning") or {}
            obs = [
                1.0 if learning.get("meta_mode") == "NORMAL" else 0.7,
            ]

        elif agent_name == "MarketAgent":
            obs = [
                snapshot["risk"]["liquidity"]["global_liquidity"],
            ]

        # Pad/truncate so MARL policies with fixed input_dim=3 stay compatible.
        while len(obs) < 3:
            obs.append(0.0)
        return obs[:3]
