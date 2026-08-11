import sys
from pathlib import Path

_PROP_ALGO = Path(__file__).resolve().parents[2]
_ROOT = _PROP_ALGO.parent
for _p in (_ROOT, _PROP_ALGO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from infra.stream import Stream
from risk.governance.governance_engine import GovernanceEngine


def main():
    gov = GovernanceEngine()
    bus = Stream()

    while True:
        risk = bus.consume("risk_stream", "gov_group", "gov_consumer")
        if not risk:
            continue

        gov_state = gov.run(
            risk["budgets"],
            risk["anomalies"],
            risk["clusters"],
            risk["liquidity"]
        )

        bus.publish("governance_stream", gov_state)


if __name__ == "__main__":
    main()
