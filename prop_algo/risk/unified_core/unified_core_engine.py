from .core_state import CoreState
from .subsystem_adapter import adapt_signals
from .signal_fusion import fuse_signals
from .stability_matrix import compute_stability
from .coherence_engine import compute_coherence
from .unified_controller import control_unified


class UnifiedCoreEngine:
    def __init__(self):
        self.state = CoreState()

    def run(self, risk_budgets, anomalies, clusters, liquidity, governance):
        signals = adapt_signals(risk_budgets, anomalies, clusters, liquidity, governance)
        vec = fuse_signals(signals)
        stability = compute_stability(vec)
        coherence = compute_coherence(signals)
        control = control_unified(stability, coherence)

        self.state.state["stability"] = stability
        self.state.state["coherence"] = coherence
        self.state.state["mode"] = control["mode"]

        return self.state.state
