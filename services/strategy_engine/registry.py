import importlib
import pkgutil
from pathlib import Path

from services.strategy_engine.base import StrategyPlugin

_registry = {}


def register(strategy_cls):
    if not issubclass(strategy_cls, StrategyPlugin):
        raise TypeError(f"{strategy_cls} must extend StrategyPlugin")
    _registry[strategy_cls.name] = strategy_cls()
    return strategy_cls


def get(name):
    return _registry.get(name)


def list_strategies():
    return list(_registry.keys())


def choose_signal(name, prices, params=None, candles=None):
    strategy = get(name)
    if not strategy:
        return "HOLD"
    if getattr(strategy, "requires_candles", False) and candles:
        return strategy.run([], params, candles)
    return strategy.run(prices, params, candles)


def schemas():
    return {name: s.param_schema() for name, s in _registry.items()}


def discover_plugins():
    plugins_pkg = "services.strategy_engine.plugins"
    package = importlib.import_module(plugins_pkg)
    prefix = plugins_pkg + "."
    for module in pkgutil.iter_modules(package.__path__, prefix):
        importlib.import_module(module.name)


def init():
    _registry.clear()
    discover_plugins()
