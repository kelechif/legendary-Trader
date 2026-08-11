class MultiAccountManager:
    def __init__(self, registry):
        self.registry = registry

    def broadcast(self, trade):
        results = []
        for name, profile in self.registry.accounts.items():
            adapter = profile["adapter"]
            results.append(adapter.place_order(
                trade["symbol"], trade["size"], trade["sl"], trade["tp"]
            ))
        return results
