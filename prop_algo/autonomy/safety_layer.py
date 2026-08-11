class SafetyLayer:
    def __init__(self):
        self.trading_enabled = True

    def evaluate(self, global_mode, stability):
        if global_mode == "SAFE_MODE" or stability < 0.2:
            self.trading_enabled = False
        else:
            self.trading_enabled = True

        return {"trading_enabled": self.trading_enabled}
