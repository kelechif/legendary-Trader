from ..multi_account.manager import MultiAccountManager


class ExecutionOptimizer:
    def __init__(self, registry, multi_account=None):
        self.registry = registry
        self.multi = multi_account or MultiAccountManager(registry)
        self._log = []

    def run(self, signals, risk_factors, size=0.1, route="MARKET"):
        results = []
        order_size = float(size) if size is not None else 0.1
        order_route = route or "MARKET"
        active = set(self.multi.active_accounts())

        for (acc, sym), sigs in signals.items():
            if active and acc not in active:
                continue
            risk = risk_factors.get(acc, 1.0)
            if risk < 0.3:
                continue

            sig = sigs["trend"]["signal"]

            if sig == "BUY":
                # Route is advisory for mission/telemetry; broker call stays a simple fill.
                res = self.multi.place_order(
                    acc, sym, order_size, None, None, route=order_route
                )
                self._log.append(
                    {
                        "account": acc,
                        "symbol": sym,
                        "route": order_route,
                        "size": order_size,
                    }
                )
                results.append(res)

        return results

    def snapshot(self):
        return {"routes": [e["route"] for e in self._log]}
