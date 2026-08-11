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
from trading.multi_account.manager import MultiAccountManager


def main():
    registry = Registry()
    kind = register_broker_accounts(registry)
    multi = MultiAccountManager(registry)
    print(f"market_data_service broker adapter={kind}", flush=True)
    print(
        f"market_data_service multi_account="
        f"{'on' if multi.enabled() else 'off'} "
        f"accounts={multi.account_count()}",
        flush=True,
    )

    bus = Stream()
    metrics = Metrics(8000)

    while True:
        market_data = registry.get_all_history()
        for name, info in multi.snapshot().items():
            equity = info.get("equity")
            if equity is not None:
                metrics.equity.labels(account=name).set(float(equity))
        bus.publish("market_data_stream", market_data)
        time.sleep(1)


if __name__ == "__main__":
    main()
