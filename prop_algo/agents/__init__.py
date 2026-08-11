"""Agent stubs package.

MARL/torch-backed symbols are lazy so light services can import agent helpers
without requiring torch at package import time.
"""

from .base_agent import BaseAgent
from .strategy_agent import StrategyAgent
from .risk_agent import RiskAgent
from .execution_agent import ExecutionAgent
from .governance_agent import GovernanceAgent
from .research_agent import ResearchAgent
from .market_agent import MarketAgent
from .agent_controller import AgentController
from .agent_protocol import AgentProtocol, negotiate
from .agent_memory import AgentMemory
from .agent_rewards import AgentRewards, compute_rewards
from .multi_agent_engine import MultiAgentEngine

__all__ = [
    "BaseAgent",
    "StrategyAgent",
    "RiskAgent",
    "ExecutionAgent",
    "GovernanceAgent",
    "ResearchAgent",
    "MarketAgent",
    "AgentController",
    "AgentProtocol",
    "negotiate",
    "AgentMemory",
    "AgentRewards",
    "compute_rewards",
    "AgentPolicy",
    "observations_to_intent_logits",
    "AgentTrainer",
    "MARLAgent",
    "MARLController",
    "MultiAgentEnv",
    "MultiAgentEngine",
]

_LAZY = {
    "AgentPolicy": (".agent_policy", "AgentPolicy"),
    "observations_to_intent_logits": (".agent_policy", "observations_to_intent_logits"),
    "AgentTrainer": (".agent_trainer", "AgentTrainer"),
    "MARLAgent": (".marl_agent", "MARLAgent"),
    "MARLController": (".marl_controller", "MARLController"),
    "MultiAgentEnv": (".multi_agent_env", "MultiAgentEnv"),
}


def __getattr__(name: str):
    if name in _LAZY:
        mod_name, attr = _LAZY[name]
        import importlib

        mod = importlib.import_module(mod_name, __name__)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
