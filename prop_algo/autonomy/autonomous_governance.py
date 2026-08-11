class AutonomousGovernance:
    def __init__(self):
        self.state = {"exec_mode": "ADAPTIVE"}

    def update(self, alerts):
        if "Liquidity stress" in alerts:
            self.state["exec_mode"] = "LIMIT_ONLY"

        elif "System instability" in alerts:
            self.state["exec_mode"] = "SAFE_EXEC"

        else:
            self.state["exec_mode"] = "ADAPTIVE"

        return self.state
