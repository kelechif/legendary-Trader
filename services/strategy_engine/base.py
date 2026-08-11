from abc import ABC, abstractmethod


class StrategyPlugin(ABC):
    name: str = "BaseStrategy"
    description: str = ""
    default_params: dict = {}
    requires_candles: bool = False

    @classmethod
    def param_schema(cls):
        return {k: {"default": v, "type": type(v).__name__} for k, v in cls.default_params.items()}

    @abstractmethod
    def signal(self, prices, params=None, candles=None):
        """Return BUY, SELL, or HOLD."""
        pass

    def run(self, prices, params=None, candles=None):
        merged = dict(self.default_params)
        if params:
            merged.update(params)
        return self.signal(prices, merged, candles)
