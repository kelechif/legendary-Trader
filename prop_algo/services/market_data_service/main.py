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


def main():
    registry = Registry()
    kind = register_broker_accounts(registry)
    print(f"market_data_service broker adapter={kind}", flush=True)

    bus = Stream()
    metrics = Metrics(8000)

    while True:
        market_data = registry.get_all_history()
        for name, profile in registry.accounts.items():
            adapter = profile["adapter"]
            info = adapter.get_account_info()
            metrics.equity.labels(account=name).set(info["equity"])
        bus.publish("market_data_stream", market_data)
        time.sleep(1)


if __name__ == "__main__":
    main()
