class ExecutionOptimizer:
    def __init__(self, registry):
        self.registry = registry
        self._log = []

    def run(self, signals, risk_factors):
        results = []
        for (acc, sym), sigs in signals.items():
            risk = risk_factors.get(acc, 1.0)
            if risk < 0.3:
                continue

            adapter = self.registry.accounts[acc]["adapter"]
            sig = sigs["trend"]["signal"]

            if sig == "BUY":
                res = adapter.place_order(sym, 0.1, None, None)
                self._log.append({"account": acc, "symbol": sym, "route": "MARKET"})
                results.append(res)

        return results

    def snapshot(self):
        return {"routes": [e["route"] for e in self._log]}
