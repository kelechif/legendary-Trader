class Registry:
    def __init__(self):
        self.accounts = {}

    def register_account(self, name, adapter, rules=None):
        self.accounts[name] = {"adapter": adapter, "rules": rules or {}}

    def get_all_history(self):
        data = {}
        for name, profile in self.accounts.items():
            adapter = profile["adapter"]
            for sym in adapter.get_open_symbols():
                data[(name, sym)] = adapter.get_history(sym)
        return data

    def snapshot_accounts(self):
        return {
            name: profile["adapter"].get_account_info()
            for name, profile in self.accounts.items()
        }
