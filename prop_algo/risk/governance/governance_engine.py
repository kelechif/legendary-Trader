from .governance_state import GovernanceState
from .global_metrics import collect_global_metrics
from .conflict_detector import detect_conflicts
from .stability_engine import apply_stability_actions
from .governance_rules import enforce_governance_rules


class GovernanceEngine:
    def __init__(self):
        self.state = GovernanceState()

    def run(self, risk_budgets, anomalies, clusters, liquidity):
        metrics = collect_global_metrics(risk_budgets, anomalies, clusters, liquidity)
        conflicts = detect_conflicts(metrics)
        actions = apply_stability_actions(conflicts, self.state.state)
        rules = enforce_governance_rules(self.state.state)

        self.state.state["last_conflicts"] = conflicts
        self.state.save()

        return {"conflicts": conflicts, "actions": actions, "rules": rules}
