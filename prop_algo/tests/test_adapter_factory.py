"""Unit tests for env-driven broker adapter factory (no live brokers/network)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from prop_algo.core.adapters.factory import (
    AdapterConfigError,
    account_names_for_kind,
    create_adapter,
    get_broker_adapter_kind,
    register_broker_accounts,
)
from prop_algo.core.adapters.mock_adapter import MockAdapter
from prop_algo.core.registry.registry import Registry


class TestAdapterFactory(unittest.TestCase):
    def test_default_kind_is_mock(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_broker_adapter_kind(), "mock")
            adapter = create_adapter("ACC1")
            self.assertIsInstance(adapter, MockAdapter)
            self.assertEqual(adapter.name, "ACC1")

    def test_explicit_mock_adapter(self):
        with patch.dict(os.environ, {"BROKER_ADAPTER": "mock"}, clear=True):
            adapter = create_adapter("DEMO")
            self.assertIsInstance(adapter, MockAdapter)

    def test_invalid_adapter_raises_clear_error(self):
        with patch.dict(os.environ, {"BROKER_ADAPTER": "moomoo"}, clear=True):
            with self.assertRaises(AdapterConfigError) as ctx:
                get_broker_adapter_kind()
            self.assertIn("Unknown BROKER_ADAPTER", str(ctx.exception))
            self.assertIn("mock", str(ctx.exception))

    def test_invalid_kind_on_create_adapter(self):
        with self.assertRaises(AdapterConfigError) as ctx:
            create_adapter("ACC1", kind="not-a-broker")
        self.assertIn("Unknown BROKER_ADAPTER", str(ctx.exception))

    def test_mt5_missing_creds_raise_clear_errors(self):
        with patch.dict(os.environ, {"BROKER_ADAPTER": "mt5"}, clear=True):
            with self.assertRaises(AdapterConfigError) as ctx:
                create_adapter("ACC1")
            msg = str(ctx.exception)
            self.assertIn("MT5_LOGIN", msg)
            self.assertIn("BROKER_ADAPTER=mock", msg)

        with patch.dict(
            os.environ,
            {
                "BROKER_ADAPTER": "mt5",
                "MT5_LOGIN": "12345",
            },
            clear=True,
        ):
            with self.assertRaises(AdapterConfigError) as ctx:
                create_adapter("ACC1")
            self.assertIn("MT5_PASSWORD", str(ctx.exception))

        with patch.dict(
            os.environ,
            {
                "BROKER_ADAPTER": "mt5",
                "MT5_LOGIN": "12345",
                "MT5_PASSWORD": "secret",
            },
            clear=True,
        ):
            with self.assertRaises(AdapterConfigError) as ctx:
                create_adapter("ACC1")
            self.assertIn("MT5_SERVER", str(ctx.exception))

    def test_mt5_non_integer_login_raises(self):
        with patch.dict(
            os.environ,
            {
                "BROKER_ADAPTER": "mt5",
                "MT5_LOGIN": "not-an-int",
                "MT5_PASSWORD": "secret",
                "MT5_SERVER": "Demo",
            },
            clear=True,
        ):
            with self.assertRaises(AdapterConfigError) as ctx:
                create_adapter("ACC1")
            self.assertIn("integer", str(ctx.exception))

    def test_mt5_builds_without_connecting(self):
        """Credentials present -> adapter constructed; MetaTrader5 not required until connect()."""
        with patch.dict(
            os.environ,
            {
                "BROKER_ADAPTER": "mt5",
                "MT5_LOGIN": "42",
                "MT5_PASSWORD": "secret",
                "MT5_SERVER": "Demo-Server",
                "MT5_SYMBOLS": "EURUSD",
            },
            clear=True,
        ):
            with patch(
                "prop_algo.core.adapters.mt5_adapter.MT5Adapter", autospec=True
            ) as mock_cls:
                mock_cls.return_value = MagicMock(name="mt5")
                adapter = create_adapter("LIVE1")
                mock_cls.assert_called_once()
                kwargs = mock_cls.call_args.kwargs
                self.assertEqual(kwargs["login"], 42)
                self.assertEqual(kwargs["password"], "secret")
                self.assertEqual(kwargs["server"], "Demo-Server")
                self.assertEqual(kwargs["name"], "LIVE1")
                self.assertEqual(kwargs["symbols"], ["EURUSD"])
                self.assertIs(adapter, mock_cls.return_value)

    def test_ctrader_missing_creds_raise_clear_errors(self):
        required = [
            "CTRADER_CLIENT_ID",
            "CTRADER_CLIENT_SECRET",
            "CTRADER_ACCESS_TOKEN",
            "CTRADER_BASE_URL",
        ]
        base = {"BROKER_ADAPTER": "ctrader"}
        for i, missing in enumerate(required):
            env = dict(base)
            for name in required[:i]:
                env[name] = f"value-for-{name}"
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(AdapterConfigError) as ctx:
                    create_adapter("ACC1")
                msg = str(ctx.exception)
                self.assertIn(missing, msg)
                self.assertIn("BROKER_ADAPTER=mock", msg)

    def test_ctrader_builds_without_network(self):
        with patch.dict(
            os.environ,
            {
                "BROKER_ADAPTER": "ctrader",
                "CTRADER_CLIENT_ID": "cid",
                "CTRADER_CLIENT_SECRET": "csecret",
                "CTRADER_ACCESS_TOKEN": "token",
                "CTRADER_BASE_URL": "https://example.test/api",
            },
            clear=True,
        ):
            with patch(
                "prop_algo.core.adapters.ctrader_adapter.CTraderAdapter",
                autospec=True,
            ) as mock_cls:
                mock_cls.return_value = MagicMock(name="ctrader")
                adapter = create_adapter("CT1")
                mock_cls.assert_called_once()
                kwargs = mock_cls.call_args.kwargs
                self.assertEqual(kwargs["client_id"], "cid")
                self.assertEqual(kwargs["access_token"], "token")
                self.assertEqual(kwargs["base_url"], "https://example.test/api")
                self.assertEqual(kwargs["name"], "CT1")
                self.assertIs(adapter, mock_cls.return_value)

    def test_account_names_defaults(self):
        with patch.dict(os.environ, {"BROKER_ADAPTER": "mock"}, clear=True):
            self.assertEqual(account_names_for_kind(), ["ACC1", "ACC2"])
        with patch.dict(os.environ, {"BROKER_ADAPTER": "mt5"}, clear=True):
            self.assertEqual(account_names_for_kind(), ["ACC1"])

    def test_register_broker_accounts_mock(self):
        registry = Registry()
        with patch.dict(
            os.environ,
            {"BROKER_ADAPTER": "mock", "BROKER_ACCOUNTS": "A,B"},
            clear=True,
        ):
            kind = register_broker_accounts(registry, connect=True)
        self.assertEqual(kind, "mock")
        self.assertEqual(set(registry.accounts), {"A", "B"})
        for name in ("A", "B"):
            adapter = registry.accounts[name]["adapter"]
            self.assertIsInstance(adapter, MockAdapter)
            self.assertTrue(adapter._connected)


if __name__ == "__main__":
    unittest.main()
