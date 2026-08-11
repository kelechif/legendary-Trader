try:
    from infra.modes import NORMAL
except ImportError:  # package import as prop_algo.* (pytest / non-Docker)
    from prop_algo.infra.modes import NORMAL

from .meta_state import MetaState

class MetaLearningEngine:
    def __init__(self):
        self.state = MetaState()

    def run(self, fitness_history, anomalies, governance_state):
        avg_fitness = sum(h["fitness"] for h in fitness_history[-20:]) / max(1, len(fitness_history[-20:]))
        anomaly_pressure = len(anomalies)
        rules = (governance_state or {}).get("rules") or {}
        exec_mode = rules.get("execution_mode", NORMAL)

        mode = NORMAL

        if avg_fitness < 0 and anomaly_pressure > 3:
            mode = "STABILIZE"

        if exec_mode == "LIMIT_ONLY":
            mode = "CONSERVATIVE"

        self.state.state["meta_mode"] = mode
        self.state.state["patterns"] = [
            {"avg_fitness": avg_fitness, "anomalies": anomaly_pressure, "exec_mode": exec_mode}
        ]
        self.state.save()

        return self.state.state
