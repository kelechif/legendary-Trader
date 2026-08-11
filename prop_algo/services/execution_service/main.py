import sys
import time
from pathlib import Path

_PROP_ALGO = Path(__file__).resolve().parents[2]
_ROOT = _PROP_ALGO.parent
for _p in (_ROOT, _PROP_ALGO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.adapters.factory import register_broker_accounts
from core.registry.registry import Registry
from infra.metrics import Metrics
from infra.stream import Stream
from trading.execution.execution_optimizer import ExecutionOptimizer


def main():
    registry = Registry()
    kind = register_broker_accounts(registry)
    print(f"execution_service broker adapter={kind}", flush=True)
    exec_engine = ExecutionOptimizer(registry)
    bus = Stream()
    metrics = Metrics(8002)

    while True:
        signals = bus.consume("strategy_signal_stream", "exec_group", "exec_consumer")
        risk = bus.consume("risk_stream", "exec_group", "exec_consumer")
        gov = bus.consume("governance_stream", "exec_group", "exec_consumer")

        if not signals or not risk or not gov:
            continue

        risk_factors = risk["budgets"]

        t0 = time.perf_counter()
        exec_results = exec_engine.run(signals, risk_factors)
        latency_value = time.perf_counter() - t0
        metrics.exec_latency.set(latency_value)

        bus.publish("execution_stream", exec_results)


if __name__ == "__main__":
    main()
