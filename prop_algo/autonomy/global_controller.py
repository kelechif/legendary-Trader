class GlobalController:
    def __init__(self):
        self.mode = "NORMAL"

    def update(self, stability, coherence, alerts, evolution_flag):
        if "System instability" in alerts:
            self.mode = "SAFE_MODE"

        elif evolution_flag:
            self.mode = "EVOLUTION"

        elif coherence < 0.5:
            self.mode = "ADAPTIVE"

        else:
            self.mode = "NORMAL"

        return {"global_mode": self.mode}
