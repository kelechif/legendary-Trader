import json


class MetaState:
    def __init__(self):
        self.file = "state/meta.json"
        try:
            with open(self.file) as f:
                self.state = json.load(f)
        except:
            self.state = {"meta_mode": "NORMAL", "patterns": []}

    def save(self):
        with open(self.file, "w") as f:
            json.dump(self.state, f, indent=4)
