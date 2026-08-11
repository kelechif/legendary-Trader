class AutonomousEvolution:
    def __init__(self):
        self.threshold = 0.2

    def update(self, fitness_history):
        recent = [f["fitness"] for f in fitness_history[-10:]]
        avg = sum(recent) / max(1, len(recent))

        if avg < self.threshold:
            return {"evolve": True}

        return {"evolve": False}
