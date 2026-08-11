import json


class HyperState:
    def __init__(self):
        self.file = "state/hyper.json"
        try:
            with open(self.file) as f:
                self.state = json.load(f)
        except:
            self.state = {"best_params": {}, "history": []}

    def save(self):
        with open(self.file, "w") as f:
            json.dump(self.state, f, indent=4)
