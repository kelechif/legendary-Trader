import os
import sys
import time
from pathlib import Path

_PROP_ALGO = Path(__file__).resolve().parents[2]
_ROOT = _PROP_ALGO.parent
for _p in (_ROOT, _PROP_ALGO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.adapters.mock_adapter import MockAdapter
from core.registry.registry import Registry
from infra.metrics import Metrics
from infra.stream import Stream
from learning.hyper_optimizer.hyper_engine import HyperOptimizer
from learning.meta_learning.meta_engine import MetaLearningEngine
from learning.research_lab.lab_engine import ResearchLab
from learning.strategy_incubator.incubator_engine import StrategyIncubator
from learning.synthetic_market.synthetic_engine import SyntheticMarketEngine


def main():
    # Cap CPU: risk_stream is hot; avoid tight re-eval of growing candidate sets.
    loop_sleep = float(os.getenv("LEARNING_LOOP_SLEEP", "2"))
    num_new = max(1, int(os.getenv("LEARNING_NUM_NEW", "1")))
    history_cap = max(10, int(os.getenv("LEARNING_FITNESS_HISTORY", "100")))
    block_ms = int(os.getenv("STREAM_BLOCK_MS", "1000"))

    registry = Registry()
    registry.register_account("ACC1", MockAdapter("ACC1"))
    registry.register_account("ACC2", MockAdapter("ACC2"))
    incubator = StrategyIncubator(registry)
    lab = ResearchLab(registry)
    hyper = HyperOptimizer(registry)
    meta = MetaLearningEngine()
    synthetic = SyntheticMarketEngine(["EURUSD", "GBPUSD"])

    bus = Stream()
    metrics = Metrics(8003)
    fitness_history = []

    while True:
        risk = bus.consume(
            "risk_stream", "learn_group", "learn_consumer", block=block_ms
        )
        if not risk:
            continue

        anomalies = risk.get("anomalies", {})

        # generate candidates — only evaluate the newly added ones this cycle
        candidates_state = incubator.run(num_new=num_new)
        candidates = candidates_state["candidates"][-num_new:]

        # evaluate
        fitness = lab.run(candidates)
        for strategy_id, f in fitness.items():
            fitness_score = f["final"]
            metrics.learning_fitness.labels(strategy=strategy_id).set(fitness_score)

        # optimize
        new_params = hyper.run(fitness, candidates)

        # meta-learning
        for cid, f in fitness.items():
            fitness_history.append({"id": cid, "fitness": f["final"]})
        if len(fitness_history) > history_cap:
            del fitness_history[:-history_cap]

        meta_state = meta.run(fitness_history, anomalies, {})

        # synthetic market
        synthetic_env, corr = synthetic.generate()

        bus.publish("learning_stream", {
            "best_params": hyper.state.state["best_params"],
            "meta_mode": meta_state["meta_mode"],
            "corr": corr.tolist() if hasattr(corr, "tolist") else corr,
        })

        if loop_sleep > 0:
            time.sleep(loop_sleep)


if __name__ == "__main__":
    main()
