import random

from .incubator_state import IncubatorState


class StrategyIncubator:
    def __init__(self, registry):
        self.registry = registry
        self.state = IncubatorState()

    def _generate_candidate(self):
        return {
            "id": f"strat_{self.state.state['generation']}_{len(self.state.state['candidates'])}",
            "params": {
                "lookback": random.randint(20, 200),
                "threshold": random.uniform(0.001, 0.01),
            },
        }

    def run(self, num_new=3):
        for _ in range(num_new):
            self.state.state["candidates"].append(self._generate_candidate())
        self.state.state["generation"] += 1
        self.state.save()
        return self.state.state
