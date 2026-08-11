"""Multi-account tracking, order routing, and account snapshots.

Environment
-----------
MULTI_ACCOUNT_ENABLED  1|0  (default: 1)
  When on, execution routes across all registered accounts present in
  signals and mission exposes per-account equity/balance snapshots.
  When off, routing collapses to the first registered account.
"""

from __future__ import annotations

import os
from typing import Any, Mapping


class MultiAccountManager:
    def __init__(self, registry):
        self.registry = registry

    @staticmethod
    def enabled() -> bool:
        raw = (os.getenv("MULTI_ACCOUNT_ENABLED") or "1").strip().lower()
        return raw not in ("0", "false", "off", "no")

    def account_names(self) -> list[str]:
        return list(self.registry.accounts.keys())

    def account_count(self) -> int:
        return len(self.registry.accounts)

    def active_accounts(self) -> list[str]:
        """Accounts that participate in routing given the enable flag."""
        names = self.account_names()
        if not names:
            return []
        if self.enabled():
            return names
        return [names[0]]

    def get_adapter(self, account: str):
        try:
            return self.registry.accounts[account]["adapter"]
        except KeyError as exc:
            raise KeyError(f"Unknown account {account!r}") from exc

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Per-account equity/balance (and margin when available)."""
        out: dict[str, dict[str, Any]] = {}
        for name, profile in self.registry.accounts.items():
            try:
                info = profile["adapter"].get_account_info() or {}
            except Exception:
                info = {}
            if not isinstance(info, Mapping):
                info = {}
            out[name] = {
                "name": info.get("name", name),
                "equity": info.get("equity"),
                "balance": info.get("balance"),
                "margin": info.get("margin"),
            }
        return out

    def summary(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled(),
            "account_count": self.account_count(),
            "active_accounts": self.active_accounts(),
            "accounts": self.snapshot(),
        }

    def place_order(
        self,
        account: str,
        symbol: str,
        size: float,
        sl=None,
        tp=None,
        *,
        route: str | None = None,
    ) -> Any:
        adapter = self.get_adapter(account)
        res = adapter.place_order(symbol, size, sl, tp)
        if isinstance(res, dict):
            out = {**res, "account": account}
            if route is not None:
                out["route"] = route
            return out
        return {"account": account, "symbol": symbol, "size": size, "result": res}

    def broadcast(self, trade: Mapping[str, Any]) -> list[Any]:
        results = []
        for name in self.active_accounts():
            results.append(
                self.place_order(
                    name,
                    trade["symbol"],
                    trade["size"],
                    trade.get("sl"),
                    trade.get("tp"),
                    route=trade.get("route"),
                )
            )
        return results

    def route_order(
        self, trade: Mapping[str, Any], account: str | None = None
    ) -> list[Any]:
        """Place on one account, or broadcast across active accounts."""
        if account is not None:
            return [
                self.place_order(
                    account,
                    trade["symbol"],
                    trade["size"],
                    trade.get("sl"),
                    trade.get("tp"),
                    route=trade.get("route"),
                )
            ]
        return self.broadcast(trade)
