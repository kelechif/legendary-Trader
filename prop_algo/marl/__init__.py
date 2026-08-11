"""MARL package — policy, trainer, agents, env, controller.

Torch-backed symbols are lazy so importing ``marl`` (or light helpers that
only need env/controller types) does not require torch at package import time.
"""

__all__ = [
    "AgentPolicy",
    "observations_to_intent_logits",
    "AgentTrainer",
    "MARLAgent",
    "MultiAgentEnv",
    "MARLController",
    "MARLSimLoop",
]

_LAZY = {
    "AgentPolicy": (".policy", "AgentPolicy"),
    "observations_to_intent_logits": (".policy", "observations_to_intent_logits"),
    "AgentTrainer": (".trainer", "AgentTrainer"),
    "MARLAgent": (".marl_agent", "MARLAgent"),
    "MultiAgentEnv": (".environment", "MultiAgentEnv"),
    "MARLController": (".marl_controller", "MARLController"),
    "MARLSimLoop": (".marl_sim_loop", "MARLSimLoop"),
}


def __getattr__(name: str):
    if name in _LAZY:
        mod_name, attr = _LAZY[name]
        import importlib

        mod = importlib.import_module(mod_name, __name__)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
