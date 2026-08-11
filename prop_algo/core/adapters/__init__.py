from .base_adapter import BaseAdapter
from .factory import (
    AdapterConfigError,
    create_adapter,
    get_broker_adapter_kind,
    register_broker_accounts,
)
from .mock_adapter import MockAdapter

__all__ = [
    "BaseAdapter",
    "MockAdapter",
    "AdapterConfigError",
    "create_adapter",
    "get_broker_adapter_kind",
    "register_broker_accounts",
]

# Optional broker adapters (hard deps may be missing in test/dev envs).
try:
    from .mt5_adapter import MT5Adapter

    __all__.append("MT5Adapter")
except ImportError:
    pass

try:
    from .ctrader_adapter import CTraderAdapter

    __all__.append("CTraderAdapter")
except ImportError:
    pass

try:
    from .broker_adapter import BrokerAdapter

    __all__.append("BrokerAdapter")
except ImportError:
    pass
