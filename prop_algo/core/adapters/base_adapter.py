class BaseAdapter:
    def connect(self):
        raise NotImplementedError

    def get_account_info(self):
        raise NotImplementedError

    def get_open_symbols(self):
        raise NotImplementedError

    def get_history(self, symbol, lookback=500):
        raise NotImplementedError

    def place_order(self, symbol, size, sl, tp):
        raise NotImplementedError

    def place_limit_order(self, symbol, size, sl, tp, price):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError
