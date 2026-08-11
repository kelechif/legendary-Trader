import sys
from pathlib import Path

_PROP_ALGO = Path(__file__).resolve().parents[2]
_ROOT = _PROP_ALGO.parent
for _p in (_ROOT, _PROP_ALGO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.adapters.mock_adapter import MockAdapter
from core.registry.registry import Registry
from infra.stream import Stream
from trading.autopilot import AutopilotEngine
from trading.strategies.engine import StrategyEngine


def main():
    registry = Registry()
    registry.register_account("ACC1", MockAdapter("ACC1"))
    registry.register_account("ACC2", MockAdapter("ACC2"))
    engine = StrategyEngine(registry)
    bus = Stream()
    # Autopilot gates new orders in execution_service; strategy still publishes.
    print(
        f"strategy_service autopilot="
        f"{'on' if AutopilotEngine.enabled() else 'off'}"
        f" (orders gated in execution_service)",
        flush=True,
    )

    while True:
        data = bus.consume("market_data_stream", "strategy_group", "strategy_consumer")
        if not data:
            continue

        signals = engine.run(data)
        bus.publish("strategy_signal_stream", signals)


if __name__ == "__main__":
    main()
