import random
from .hyper_state import HyperState

class HyperOptimizer:
    def __init__(self, registry):
        self.registry = registry
        self.state = HyperState()

    def mutate(self, params):
        return {
            "lookback": max(10, params["lookback"] + random.randint(-10, 10)),
            "threshold": max(0.0001, params["threshold"] + random.uniform(-0.001, 0.001)),
        }

    def run(self, fitness_scores, candidates):
        if not fitness_scores:
            return self.state.state

        best_id = max(fitness_scores, key=lambda k: fitness_scores[k]["final"])
        best_candidate = next(c for c in candidates if c["id"] == best_id)
        best_params = best_candidate["params"]

        new_params = self.mutate(best_params)

        self.state.state["best_params"] = best_params
        self.state.state["history"].append({
            "id": best_id,
            "fitness": fitness_scores[best_id]["final"],
            "params": best_params
        })
        self.state.save()

        return new_params
