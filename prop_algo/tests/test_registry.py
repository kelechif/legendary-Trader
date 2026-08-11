from prop_algo.core.adapters.mock_adapter import MockAdapter
from prop_algo.core.registry.registry import Registry


def test_registry():
    r = Registry()
    r.register_account("A", MockAdapter("A"))
    assert "A" in r.accounts


# unittest discover collects TestCase methods; mirrors the pytest-style test above.
import unittest


class TestRegistry(unittest.TestCase):
    def test_registry(self):
        test_registry()

    def test_get_all_history(self):
        r = Registry()
        r.register_account("A", MockAdapter("A"))
        history = r.get_all_history()
        assert ("A", "EURUSD") in history
        assert "close" in history[("A", "EURUSD")].columns


if __name__ == "__main__":
    unittest.main()
