from .base_agent import BaseAgent


class RiskAgent(BaseAgent):
    def observe(self, snapshot):
        self.state["stability"] = snapshot["unified"]["stability"]
        self.state["anomalies"] = len(snapshot["risk"]["anomalies"])

    def act(self):
        if self.state["stability"] < 0.3:
            return {"intent": "REDUCE_RISK"}
        if self.state["anomalies"] > 5:
            return {"intent": "LIMIT_RISK"}
        return {"intent": "MAINTAIN_RISK"}
