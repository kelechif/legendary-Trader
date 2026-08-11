import json


class GovernanceState:
    def __init__(self):
        self.file = "state/governance.json"
        try:
            with open(self.file) as f:
                self.state = json.load(f)
        except:
            self.state = {
                "global_mode": "NORMAL",
                "last_conflicts": [],
                "last_actions": []
            }

    def save(self):
        with open(self.file, "w") as f:
            json.dump(self.state, f, indent=4)
