"""Tests MoomooBroker's own logic (code prefixing, DataFrame parsing, enum
handling) against a fake `moomoo` module, since the real SDK needs a live
OpenD gateway + moomoo account that aren't available in CI/sandboxes.
"""
import sys
import types

import pandas as pd


def _install_fake_moomoo():
    ft = types.ModuleType("moomoo")
    ft.RET_OK = 0

    class TrdEnv:
        SIMULATE = "SIMULATE"
        REAL = "REAL"

    class TrdSide:
        BUY = "BUY"
        SELL = "SELL"

    class OrderType:
        NORMAL = "NORMAL"

    class TrdMarket:
        NONE = "NONE"
        US = "US"

    ft.TrdEnv = TrdEnv
    ft.TrdSide = TrdSide
    ft.OrderType = OrderType
    ft.TrdMarket = TrdMarket

    class FakeTradeContext:
        last_place_order_kwargs = None

        def __init__(self, host, port, filter_trdmarket):
            self.host, self.port, self.filter_trdmarket = host, port, filter_trdmarket

        def get_acc_list(self):
            return 0, pd.DataFrame([
                {"acc_id": 111, "trd_env": "SIMULATE"},
                {"acc_id": 222, "trd_env": "REAL"},
            ])

        def accinfo_query(self, trd_env, acc_id, refresh_cache=True):
            return 0, pd.DataFrame([{"total_assets": 100_000.0, "cash": 90_000.0}])

        def position_list_query(self, trd_env, acc_id, refresh_cache=True):
            return 0, pd.DataFrame([{"code": "US.AAPL", "qty": 10, "cost_price": 150.0}])

        def place_order(self, trd_env, trd_side, order_type, code, qty, price, acc_id):
            FakeTradeContext.last_place_order_kwargs = dict(
                trd_env=trd_env, trd_side=trd_side, order_type=order_type,
                code=code, qty=qty, price=price, acc_id=acc_id,
            )
            return 0, pd.DataFrame([{"order_id": "abc123", "order_status": "SUBMITTED"}])

        def close(self):
            pass

    ft.OpenSecTradeContext = FakeTradeContext
    return ft


def test_moomoo_broker_resolves_acc_id_and_reads_equity(monkeypatch):
    monkeypatch.setitem(sys.modules, "moomoo", _install_fake_moomoo())
    from trading_bot.execution.broker import MoomooBroker

    broker = MoomooBroker(trd_env="SIMULATE")
    assert broker.acc_id == 111
    assert broker.get_equity() == 100_000.0


def test_moomoo_broker_get_position_prefixes_code(monkeypatch):
    monkeypatch.setitem(sys.modules, "moomoo", _install_fake_moomoo())
    from trading_bot.execution.broker import MoomooBroker

    broker = MoomooBroker()
    pos = broker.get_position("AAPL")
    assert pos is not None
    assert pos.shares == 10
    assert pos.entry_price == 150.0

    assert broker.get_position("MSFT") is None


def test_moomoo_broker_submit_order_uses_prefixed_code_and_side(monkeypatch):
    fake_module = _install_fake_moomoo()
    monkeypatch.setitem(sys.modules, "moomoo", fake_module)
    from trading_bot.execution.broker import MoomooBroker

    broker = MoomooBroker()
    result = broker.submit_order("AAPL", "BUY", 10, 150.0)

    assert result.status == "SUBMITTED"
    sent = fake_module.OpenSecTradeContext.last_place_order_kwargs
    assert sent["code"] == "US.AAPL"
    assert sent["qty"] == 10
    assert sent["trd_side"] == "BUY"


def test_moomoo_broker_acc_id_can_be_pinned(monkeypatch):
    monkeypatch.setitem(sys.modules, "moomoo", _install_fake_moomoo())
    from trading_bot.execution.broker import MoomooBroker

    broker = MoomooBroker(acc_id=999)
    assert broker.acc_id == 999
