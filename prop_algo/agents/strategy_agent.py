from .base_agent import BaseAgent


class StrategyAgent(BaseAgent):
    def observe(self, snapshot):
        self.state["fitness"] = snapshot["learning"]["best_params"]

    def act(self):
        if self.state["fitness"]["threshold"] < 0.002:
            return {"intent": "EVOLVE_STRATEGIES"}
        return {"intent": "MAINTAIN_STRATEGIES"}
