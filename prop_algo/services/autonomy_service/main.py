import sys
from pathlib import Path

_PROP_ALGO = Path(__file__).resolve().parents[2]
_ROOT = _PROP_ALGO.parent
for _p in (_ROOT, _PROP_ALGO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from infra.stream import Stream
from autonomy.autonomous_engine import AutonomousEngine


def main():
    bus = Stream()
    engine = AutonomousEngine()
    fitness_history = []

    while True:
        snapshot = bus.consume("mission_stream", "auto_group", "auto_consumer")
        learning = bus.consume("learning_stream", "auto_group", "auto_consumer")

        if learning:
            fitness_history.append({"fitness": learning["best_params"].get("fitness", 0)})

        if snapshot:
            auto_state = engine.run(snapshot, fitness_history)
            bus.publish("autonomy_stream", auto_state)


if __name__ == "__main__":
    main()
