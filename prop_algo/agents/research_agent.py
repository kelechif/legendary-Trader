from .base_agent import BaseAgent


class ResearchAgent(BaseAgent):
    def observe(self, snapshot):
        self.state["meta_mode"] = snapshot["learning"]["meta_mode"]

    def act(self):
        if self.state["meta_mode"] == "STABILIZE":
            return {"intent": "RESEARCH_STABILITY"}
        return {"intent": "RESEARCH_NORMAL"}
