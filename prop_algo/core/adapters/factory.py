"""Env-driven broker adapter factory.

Compose / Docker light+torch images default to mock. Live brokers (MT5, cTrader)
are for host/local runs with the required packages and credentials.

Environment
-----------
BROKER_ADAPTER   mock | mt5 | ctrader   (default: mock)
BROKER_ACCOUNTS  comma-separated account ids
                 (default: ACC1,ACC2 for mock; ACC1 for mt5/ctrader)

MT5 (Windows host + MetaTrader5 package; not for Linux Docker):
  MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
  MT5_PATH       optional terminal path
  MT5_SYMBOLS    optional watchlist (default: EURUSD,GBPUSD)

cTrader:
  CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET, CTRADER_ACCESS_TOKEN
  CTRADER_BASE_URL   (required)
  CTRADER_SYMBOLS    optional watchlist (default: EURUSD,GBPUSD)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .base_adapter import BaseAdapter
from .mock_adapter import MockAdapter

if TYPE_CHECKING:
    from core.registry.registry import Registry

SUPPORTED_ADAPTERS = ("mock", "mt5", "ctrader")


class AdapterConfigError(RuntimeError):
    """Missing/invalid broker configuration or unavailable dependency."""


def get_broker_adapter_kind() -> str:
    kind = (os.getenv("BROKER_ADAPTER") or "mock").strip().lower()
    if kind not in SUPPORTED_ADAPTERS:
        raise AdapterConfigError(
            f"Unknown BROKER_ADAPTER={kind!r}. "
            f"Supported: {', '.join(SUPPORTED_ADAPTERS)}."
        )
    return kind


def _split_csv(value: str | None, default: str) -> list[str]:
    raw = (value or default).strip()
    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        raise AdapterConfigError("Account/symbol list is empty after parsing.")
    return names


def account_names_for_kind(kind: str | None = None) -> list[str]:
    kind = kind or get_broker_adapter_kind()
    default = "ACC1,ACC2" if kind == "mock" else "ACC1"
    return _split_csv(os.getenv("BROKER_ACCOUNTS"), default)


def _require_env(name: str, adapter: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise AdapterConfigError(
            f"{adapter} requires {name}. "
            f"Set it in the environment, or use BROKER_ADAPTER=mock."
        )
    return value


def _symbols(env_name: str) -> list[str]:
    return _split_csv(os.getenv(env_name), "EURUSD,GBPUSD")


def create_adapter(account_name: str, kind: str | None = None) -> BaseAdapter:
    """Build one adapter instance for *account_name* from env config."""
    kind = kind or get_broker_adapter_kind()

    if kind == "mock":
        return MockAdapter(account_name)

    if kind == "mt5":
        from .mt5_adapter import MT5Adapter

        login_raw = _require_env("MT5_LOGIN", "MT5Adapter")
        try:
            login = int(login_raw)
        except ValueError as exc:
            raise AdapterConfigError(
                f"MT5_LOGIN must be an integer account number, got {login_raw!r}."
            ) from exc
        password = _require_env("MT5_PASSWORD", "MT5Adapter")
        server = _require_env("MT5_SERVER", "MT5Adapter")
        path = (os.getenv("MT5_PATH") or "").strip() or None
        return MT5Adapter(
            login=login,
            password=password,
            server=server,
            path=path,
            name=account_name,
            symbols=_symbols("MT5_SYMBOLS"),
        )

    if kind == "ctrader":
        from .ctrader_adapter import CTraderAdapter

        return CTraderAdapter(
            client_id=_require_env("CTRADER_CLIENT_ID", "CTraderAdapter"),
            client_secret=_require_env("CTRADER_CLIENT_SECRET", "CTraderAdapter"),
            access_token=_require_env("CTRADER_ACCESS_TOKEN", "CTraderAdapter"),
            base_url=_require_env("CTRADER_BASE_URL", "CTraderAdapter"),
            name=account_name,
            symbols=_symbols("CTRADER_SYMBOLS"),
        )

    raise AdapterConfigError(
        f"Unknown BROKER_ADAPTER={kind!r}. "
        f"Supported: {', '.join(SUPPORTED_ADAPTERS)}."
    )


def register_broker_accounts(registry: "Registry", *, connect: bool = True) -> str:
    """Register env-configured accounts on *registry*. Returns adapter kind."""
    kind = get_broker_adapter_kind()
    for name in account_names_for_kind(kind):
        adapter = create_adapter(name, kind)
        if connect:
            adapter.connect()
        registry.register_account(name, adapter)
    return kind
