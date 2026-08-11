from .autonomous_risk import AutonomousRisk
from .autonomous_evolution import AutonomousEvolution
from .autonomous_governance import AutonomousGovernance
from .global_controller import GlobalController
from .safety_layer import SafetyLayer


class AutonomousEngine:
    def __init__(self):
        self.risk = AutonomousRisk()
        self.evolution = AutonomousEvolution()
        self.gov = AutonomousGovernance()
        self.controller = GlobalController()
        self.safety = SafetyLayer()

    def run(self, snapshot, fitness_history):
        stability = snapshot["unified"]["stability"]
        coherence = snapshot["unified"]["coherence"]
        alerts = snapshot["alerts"]
        liquidity = snapshot["risk"]["liquidity"]["global_liquidity"]
        anomalies = len(snapshot["risk"]["anomalies"])

        risk_state = self.risk.update(stability, anomalies, liquidity)
        evolution_flag = self.evolution.update(fitness_history)
        gov_state = self.gov.update(alerts)
        global_mode = self.controller.update(
            stability, coherence, alerts, evolution_flag["evolve"]
        )
        safety_state = self.safety.evaluate(global_mode["global_mode"], stability)

        return {
            "risk": risk_state,
            "governance": gov_state,
            "global_mode": global_mode["global_mode"],
            "safety": safety_state
        }
