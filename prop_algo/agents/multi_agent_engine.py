from .strategy_agent import StrategyAgent
from .risk_agent import RiskAgent
from .execution_agent import ExecutionAgent
from .governance_agent import GovernanceAgent
from .research_agent import ResearchAgent
from .market_agent import MarketAgent
from .agent_controller import AgentController


class MultiAgentEngine:
    def __init__(self):
        self.controller = AgentController([
            StrategyAgent("StrategyAgent"),
            RiskAgent("RiskAgent"),
            ExecutionAgent("ExecutionAgent"),
            GovernanceAgent("GovernanceAgent"),
            ResearchAgent("ResearchAgent"),
            MarketAgent("MarketAgent")
        ])

    def run(self, snapshot):
        return self.controller.step(snapshot)
