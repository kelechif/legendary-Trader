from .base_agent import BaseAgent


class ExecutionAgent(BaseAgent):
    def observe(self, snapshot):
        self.state["route"] = snapshot["execution"]["route"]
        self.state["slippage"] = snapshot["execution"]["slippage"]

    def act(self):
        if self.state["slippage"] > 0.001:
            return {"intent": "SWITCH_TO_LIMIT"}
        return {"intent": "MAINTAIN_EXECUTION"}
