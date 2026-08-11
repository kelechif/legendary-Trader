"""Autonomy / multi-agent orchestration.

``MultiAgentEngine`` is lazy: importing light autonomy modules (governance,
risk, evolution) must not require agents/MARL/torch.
"""

from .autonomous_engine import AutonomousEngine
from .autonomous_evolution import AutonomousEvolution
from .autonomous_governance import AutonomousGovernance
from .autonomous_risk import AutonomousRisk
from .global_controller import GlobalController
from .safety_layer import SafetyLayer

__all__ = [
    "AutonomousEngine",
    "AutonomousRisk",
    "AutonomousEvolution",
    "AutonomousGovernance",
    "GlobalController",
    "MultiAgentEngine",
    "SafetyLayer",
]


def __getattr__(name: str):
    if name == "MultiAgentEngine":
        from .multi_agent_engine import MultiAgentEngine

        return MultiAgentEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
