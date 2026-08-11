class AutonomousRisk:
    def __init__(self):
        self.state = {"risk_multiplier": 1.0}

    def update(self, stability, anomalies, liquidity):
        if stability < 0.3:
            self.state["risk_multiplier"] *= 0.8

        if anomalies > 5:
            self.state["risk_multiplier"] *= 0.9

        if liquidity < 0.5:
            self.state["risk_multiplier"] *= 0.85

        self.state["risk_multiplier"] = max(0.1, min(1.0, self.state["risk_multiplier"]))
        return self.state
