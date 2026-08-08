"""Tests for the scanner/one-click-trade preview + exit-monitoring methods
added to TradingBot and OptionsTradingBot (used by the dashboard's Scanner
tab). All network calls (price fetch, option chain) are monkeypatched out."""
from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.execution.broker import OptionPosition, PaperBroker, Position
from trading_bot.execution.options_trader import OptionsTradingBot
from trading_bot.execution.trader import TradingBot
from trading_bot.options.selector import SelectedContract
from trading_bot.options.strategy import signal_to_option_intent
from trading_bot.strategy.signals import Signal, TradeSignal

MODEL_CFG = {
    "type": "random_forest", "n_estimators": 50, "max_depth": 4,
    "lookahead_bars": 1, "up_threshold_pct": 0.0, "train_test_split": 0.8,
    "min_probability": 0.55,
}
RISK_CFG = {
    "risk_per_trade_pct": 0.01, "stop_loss_atr_mult": 2.0, "take_profit_atr_mult": 3.0,
    "max_position_pct": 0.25, "max_open_positions": 5, "daily_loss_limit_pct": 0.03,
}
OPTIONS_CFG = {
    "risk_free_rate": 0.04, "target_dte_days": 30,
    "target_delta_call": 0.6, "target_delta_put": 0.6,
    "otm_pct": 0.0, "iv_lookback": 20,
    "risk": {"risk_per_trade_pct": 0.01, "max_position_pct": 0.10,
             "take_profit_pct": 0.75, "stop_loss_pct": 0.50},
}


def _equity_config() -> dict:
    return {"data": {"interval": "1d", "history_period": "2y"}, "model": MODEL_CFG, "risk": RISK_CFG}


def _options_config() -> dict:
    return {"data": {"interval": "1d", "history_period": "2y"}, "model": MODEL_CFG, "options": OPTIONS_CFG}


@pytest.fixture
def paper_broker(tmp_path):
    return PaperBroker(starting_cash=100_000, account_file=str(tmp_path / "acct.json"))


# ---------------------------------------------------------------------------
# TradingBot (equity/futures)
# ---------------------------------------------------------------------------

def test_plan_for_evaluation_buy_returns_a_priced_plan(paper_broker):
    bot = TradingBot(_equity_config(), broker=paper_broker)
    evaluation = {"symbol": "AAPL", "signal": TradeSignal(Signal.BUY, 0.7, "x"), "price": 100.0, "atr": 2.0}

    plan = bot.plan_for_evaluation(evaluation)

    assert plan is not None
    assert plan.shares > 0
    assert plan.stop_loss < 100.0 < plan.take_profit


@pytest.mark.parametrize("signal", [Signal.SELL, Signal.HOLD])
def test_plan_for_evaluation_non_buy_returns_none(paper_broker, signal):
    bot = TradingBot(_equity_config(), broker=paper_broker)
    evaluation = {"symbol": "AAPL", "signal": TradeSignal(signal, 0.5, "x"), "price": 100.0, "atr": 2.0}

    assert bot.plan_for_evaluation(evaluation) is None


def test_submit_plan_trades_the_exact_previewed_numbers(paper_broker):
    bot = TradingBot(_equity_config(), broker=paper_broker)
    evaluation = {"symbol": "AAPL", "signal": TradeSignal(Signal.BUY, 0.7, "x"), "price": 100.0, "atr": 2.0}
    plan = bot.plan_for_evaluation(evaluation)

    result = bot.submit_plan("AAPL", 100.0, plan)

    assert result.status == "filled"
    position = paper_broker.get_position("AAPL")
    assert position is not None
    assert (position.shares, position.stop_loss, position.take_profit) == (plan.shares, plan.stop_loss, plan.take_profit)


def test_check_exits_closes_position_that_breached_stop_loss(monkeypatch, paper_broker):
    bot = TradingBot(_equity_config(), broker=paper_broker)
    paper_broker.positions["AAPL"] = Position("AAPL", shares=10, entry_price=100.0, stop_loss=95.0, take_profit=120.0)
    monkeypatch.setattr(
        "trading_bot.data.fetcher.DataFetcher.fetch",
        lambda self, symbol, period="2y", interval="1d": pd.DataFrame({"close": [90.0]}),
    )

    closed = bot.check_exits()

    assert [c["reason"] for c in closed] == ["stop_loss"]
    assert paper_broker.get_position("AAPL") is None


def test_check_exits_closes_position_that_breached_take_profit(monkeypatch, paper_broker):
    bot = TradingBot(_equity_config(), broker=paper_broker)
    paper_broker.positions["AAPL"] = Position("AAPL", shares=10, entry_price=100.0, stop_loss=95.0, take_profit=120.0)
    monkeypatch.setattr(
        "trading_bot.data.fetcher.DataFetcher.fetch",
        lambda self, symbol, period="2y", interval="1d": pd.DataFrame({"close": [125.0]}),
    )

    closed = bot.check_exits()

    assert [c["reason"] for c in closed] == ["take_profit"]
    assert paper_broker.get_position("AAPL") is None


def test_check_exits_leaves_position_open_inside_the_band(monkeypatch, paper_broker):
    bot = TradingBot(_equity_config(), broker=paper_broker)
    paper_broker.positions["AAPL"] = Position("AAPL", shares=10, entry_price=100.0, stop_loss=95.0, take_profit=120.0)
    monkeypatch.setattr(
        "trading_bot.data.fetcher.DataFetcher.fetch",
        lambda self, symbol, period="2y", interval="1d": pd.DataFrame({"close": [105.0]}),
    )

    assert bot.check_exits() == []
    assert paper_broker.get_position("AAPL") is not None


# ---------------------------------------------------------------------------
# OptionsTradingBot
# ---------------------------------------------------------------------------

_CONTRACT = SelectedContract(
    contract_symbol="AAPL240101C00100000", strike=100.0, expiration="2024-01-01",
    dte_days=30, right="call", premium=2.0, implied_vol=0.3, delta=0.6,
)


def test_options_plan_for_evaluation_previews_without_ordering(monkeypatch, paper_broker):
    bot = OptionsTradingBot(_options_config(), broker=paper_broker)
    monkeypatch.setattr(bot, "_select_contract", lambda symbol, price, right: _CONTRACT)
    signal = TradeSignal(Signal.BUY, 0.7, "bullish")
    evaluation = {"symbol": "AAPL", "signal": signal, "intent": signal_to_option_intent(signal),
                  "prediction": {"probability_up": 0.7}, "price": 100.0}

    preview = bot.plan_for_evaluation(evaluation)

    assert preview is not None
    assert preview.contract.contract_symbol == "AAPL240101C00100000"
    assert preview.plan.contracts > 0
    assert paper_broker.option_positions == {}  # preview only, nothing submitted


def test_options_plan_for_evaluation_hold_returns_none(paper_broker):
    bot = OptionsTradingBot(_options_config(), broker=paper_broker)
    signal = TradeSignal(Signal.HOLD, 0.5, "flat")
    evaluation = {"symbol": "AAPL", "signal": signal, "intent": signal_to_option_intent(signal),
                  "prediction": {"probability_up": 0.5}, "price": 100.0}

    assert bot.plan_for_evaluation(evaluation) is None


def test_options_submit_preview_trades_the_exact_previewed_contract(monkeypatch, paper_broker):
    bot = OptionsTradingBot(_options_config(), broker=paper_broker)
    monkeypatch.setattr(bot, "_select_contract", lambda symbol, price, right: _CONTRACT)
    signal = TradeSignal(Signal.BUY, 0.7, "bullish")
    evaluation = {"symbol": "AAPL", "signal": signal, "intent": signal_to_option_intent(signal),
                  "prediction": {"probability_up": 0.7}, "price": 100.0}
    preview = bot.plan_for_evaluation(evaluation)

    result = bot.submit_preview("AAPL", preview)

    assert result.status == "filled"
    position = paper_broker.get_option_position("AAPL240101C00100000")
    assert position is not None
    assert position.contracts == preview.plan.contracts


def test_options_check_exits_closes_on_take_profit(monkeypatch, paper_broker):
    bot = OptionsTradingBot(_options_config(), broker=paper_broker)
    paper_broker.option_positions["AAPL240101C00100000"] = OptionPosition(
        contract_symbol="AAPL240101C00100000", underlying="AAPL", right="call",
        strike=100.0, expiration="2024-01-01", contracts=2, entry_premium=2.0,
    )
    monkeypatch.setattr(bot.chain_fetcher, "quote_contract", lambda *a, **k: 4.0)  # +100% >= 75% TP

    closed = bot.check_exits()

    assert [c["reason"] for c in closed] == ["take_profit"]
    assert paper_broker.get_option_position("AAPL240101C00100000") is None


def test_options_check_exits_leaves_position_open_inside_the_band(monkeypatch, paper_broker):
    bot = OptionsTradingBot(_options_config(), broker=paper_broker)
    paper_broker.option_positions["AAPL240101C00100000"] = OptionPosition(
        contract_symbol="AAPL240101C00100000", underlying="AAPL", right="call",
        strike=100.0, expiration="2024-01-01", contracts=2, entry_premium=2.0,
    )
    monkeypatch.setattr(bot.chain_fetcher, "quote_contract", lambda *a, **k: 2.1)

    assert bot.check_exits() == []
    assert paper_broker.get_option_position("AAPL240101C00100000") is not None


def test_options_close_position_public_method(monkeypatch, paper_broker):
    bot = OptionsTradingBot(_options_config(), broker=paper_broker)
    position = OptionPosition(
        contract_symbol="AAPL240101C00100000", underlying="AAPL", right="call",
        strike=100.0, expiration="2024-01-01", contracts=2, entry_premium=2.0,
    )
    paper_broker.option_positions["AAPL240101C00100000"] = position
    monkeypatch.setattr(bot.chain_fetcher, "quote_contract", lambda *a, **k: 2.5)

    bot.close_position("AAPL", position)

    assert paper_broker.get_option_position("AAPL240101C00100000") is None
