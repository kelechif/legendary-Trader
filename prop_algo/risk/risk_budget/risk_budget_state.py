import json


class RiskBudgetState:
    def __init__(self):
        self.file = "state/risk_budget.json"
        try:
            with open(self.file) as f:
                self.state = json.load(f)
        except:
            self.state = {"accounts": {}}

    def save(self):
        with open(self.file, "w") as f:
            json.dump(self.state, f, indent=4)
