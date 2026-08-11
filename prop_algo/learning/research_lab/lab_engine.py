from .backtester import Backtester
from .fitness import compute_fitness
from .walkforward import walkforward
from .robustness import robustness_test


class ResearchLab:
    def __init__(self, registry):
        self.registry = registry

    def run(self, candidates):
        fitness = {}
        for c in candidates:
            df = self.registry.get_all_history()[("ACC1", "EURUSD")]  # example

            bt = Backtester(df, c["params"])
            pnl = bt.run()
            metrics = compute_fitness(pnl)

            wf = walkforward(df, c["params"])
            rb = robustness_test(df, c["params"])

            final_score = (
                0.6 * metrics["fitness"] +
                0.2 * wf +
                0.2 * rb
            )

            fitness[c["id"]] = {
                "metrics": metrics,
                "walkforward": wf,
                "robustness": rb,
                "final": final_score
            }

        return fitness
