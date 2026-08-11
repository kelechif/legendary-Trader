class ExecutionOptimizer:
    def __init__(self, registry):
        self.registry = registry
        self._log = []

    def run(self, signals, risk_factors, size=0.1, route="MARKET"):
        results = []
        order_size = float(size) if size is not None else 0.1
        order_route = route or "MARKET"
        for (acc, sym), sigs in signals.items():
            risk = risk_factors.get(acc, 1.0)
            if risk < 0.3:
                continue

            adapter = self.registry.accounts[acc]["adapter"]
            sig = sigs["trend"]["signal"]

            if sig == "BUY":
                # Route is advisory for mission/telemetry; broker call stays a simple fill.
                res = adapter.place_order(sym, order_size, None, None)
                if isinstance(res, dict):
                    res = {**res, "route": order_route}
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
