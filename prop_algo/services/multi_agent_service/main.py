import sys
from pathlib import Path

_PROP_ALGO = Path(__file__).resolve().parents[2]
_ROOT = _PROP_ALGO.parent
for _p in (_ROOT, _PROP_ALGO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from infra.stream import Stream
from autonomy.multi_agent_engine import MultiAgentEngine


def main():
    bus = Stream()
    engine = MultiAgentEngine()

    while True:
        snapshot = bus.consume("mission_stream", "ma_group", "ma_consumer")
        if snapshot:
            result = engine.run(snapshot)
            bus.publish("autonomy_stream", result)


if __name__ == "__main__":
    main()
