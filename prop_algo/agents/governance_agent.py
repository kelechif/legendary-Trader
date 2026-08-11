from .base_agent import BaseAgent


class GovernanceAgent(BaseAgent):
    def observe(self, snapshot):
        self.state["alerts"] = snapshot["alerts"]

    def act(self):
        if "System instability" in self.state["alerts"]:
            return {"intent": "SAFE_MODE"}
        return {"intent": "NORMAL_MODE"}
