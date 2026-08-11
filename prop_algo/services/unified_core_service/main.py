import sys
from pathlib import Path

_PROP_ALGO = Path(__file__).resolve().parents[2]
_ROOT = _PROP_ALGO.parent
for _p in (_ROOT, _PROP_ALGO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from infra.metrics import Metrics
from infra.modes import MODE_TO_INT
from infra.stream import Stream
from risk.unified_core.unified_core_engine import UnifiedCoreEngine


def main():
    unified = UnifiedCoreEngine()
    bus = Stream()
    metrics = None

    while True:
        risk = bus.consume("risk_stream", "unified_group", "unified_consumer")
        gov = bus.consume("governance_stream", "unified_group", "unified_consumer")

        if not risk or not gov:
            continue

        state = unified.run(
            risk["budgets"],
            risk["anomalies"],
            risk["clusters"],
            risk["liquidity"],
            gov
        )

        if metrics is None:
            metrics = Metrics(8004)
        metrics.unified_mode.set(MODE_TO_INT.get(state.get("mode"), -1))

        bus.publish("unified_core_stream", state)


if __name__ == "__main__":
    main()
