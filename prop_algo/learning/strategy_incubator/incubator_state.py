import json


class IncubatorState:
    def __init__(self):
        self.file = "state/incubator.json"
        try:
            with open(self.file) as f:
                self.state = json.load(f)
        except:
            self.state = {"candidates": [], "generation": 0}

    def save(self):
        with open(self.file, "w") as f:
            json.dump(self.state, f, indent=4)
