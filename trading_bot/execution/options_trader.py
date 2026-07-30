from __future__ import annotations

import time
from typing import Any

from trading_bot.data.fetcher import DataFetcher
from trading_bot.execution.broker import PaperBroker
from trading_bot.execution.trader import build_broker
from trading_bot.logger import get_logger
from trading_bot.ml.model import DirectionModel, load_or_train_model
from trading_bot.options.chain import OptionsChainFetcher
from trading_bot.options.risk import OptionsRiskManager, OptionsRiskParams
from trading_bot.options.selector import ContractSelector
from trading_bot.options.strategy import signal_to_option_intent
from trading_bot.strategy.signals import SignalGenerator

logger = get_logger(__name__)


class OptionsTradingBot:
    """Directional long-calls/long-puts trading loop: reuses the equity ML
    signal to pick a side, then fetches the live option chain, selects a
    contract by target delta, sizes it by premium-at-risk, and paper-trades it.

    Uses the same PaperBroker (and thus the same cash/account file) as the
    equity TradingBot by default, so both can share one paper account.
    """

    def __init__(self, config: dict[str, Any], broker: PaperBroker | None = None):
        self.config = config
        opts_cfg = config["options"]

        self.fetcher = DataFetcher()
        self.chain_fetcher = OptionsChainFetcher()
        self.selector = ContractSelector(risk_free_rate=opts_cfg["risk_free_rate"])
        self.signal_generator = SignalGenerator(min_probability=config["model"]["min_probability"])
        self.risk_manager = OptionsRiskManager(OptionsRiskParams(**opts_cfg["risk"]))
        self.broker = broker or build_broker(config)
        if not isinstance(self.broker, PaperBroker):
            raise ValueError("Options trading currently only supports the PaperBroker (paper mode).")
        self._models: dict[str, DirectionModel] = {}

    def _get_model(self, symbol: str, raw_df) -> DirectionModel:
        if symbol not in self._models:
            self._models[symbol] = load_or_train_model(symbol, raw_df, self.config["model"])
        return self._models[symbol]

    def evaluate_symbol(self, symbol: str) -> dict[str, Any]:
        data_cfg = self.config["data"]
        raw_df = self.fetcher.fetch(symbol, period=data_cfg["history_period"], interval=data_cfg["interval"])

        model = self._get_model(symbol, raw_df)
        prediction = model.predict_latest(raw_df)
        signal = self.signal_generator.generate(raw_df, prediction["probability_up"])
        intent = signal_to_option_intent(signal)

        return {
            "symbol": symbol,
            "signal": signal,
            "intent": intent,
            "prediction": prediction,
            "price": float(raw_df["close"].iloc[-1]),
        }

    def act_on_evaluation(self, evaluation: dict[str, Any]) -> None:
        symbol = evaluation["symbol"]
        intent = evaluation["intent"]
        price = evaluation["price"]
        opts_cfg = self.config["options"]

        existing = self.broker.find_option_position_for_underlying(symbol)

        if intent.right is None:
            logger.info("%s: %s -> no options action", symbol, intent.reason)
            return

        if existing is not None:
            if existing.right == intent.right:
                logger.info("%s: already holding a %s position, skipping", symbol, existing.right)
                return
            self._close_position(symbol, existing)

        expiration = self.chain_fetcher.nearest_expiration(symbol, opts_cfg["target_dte_days"])
        calls, puts = self.chain_fetcher.fetch_chain(symbol, expiration)
        chain_df = calls if intent.right == "call" else puts
        target_delta = opts_cfg["target_delta_call"] if intent.right == "call" else opts_cfg["target_delta_put"]

        contract = self.selector.select(chain_df, price, expiration, intent.right, target_delta)
        plan = self.risk_manager.plan(self.broker.get_equity(), contract.premium)

        if plan.contracts <= 0:
            logger.info("%s: risk-sized contracts == 0 for %s premium %.2f, skipping",
                        symbol, contract.contract_symbol, contract.premium)
            return

        self.broker.submit_option_order(
            contract.contract_symbol, symbol, intent.right, contract.strike, expiration,
            plan.contracts, contract.premium, "BUY_TO_OPEN",
        )

    def _close_position(self, symbol: str, position) -> None:
        premium = self.chain_fetcher.quote_contract(symbol, position.expiration, position.contract_symbol,
                                                       position.right)
        self.broker.submit_option_order(
            position.contract_symbol, symbol, position.right, position.strike, position.expiration,
            position.contracts, premium, "SELL_TO_CLOSE",
        )

    def run_once(self, symbols: list[str]) -> list[dict[str, Any]]:
        results = []
        for symbol in symbols:
            try:
                evaluation = self.evaluate_symbol(symbol)
                self.act_on_evaluation(evaluation)
                results.append(evaluation)
            except Exception as exc:  # noqa: BLE001 - one bad symbol shouldn't kill the run
                logger.exception("Failed to evaluate options for %s: %s", symbol, exc)
        return results

    def run_loop(self, symbols: list[str], poll_interval_seconds: int | None = None) -> None:
        interval = poll_interval_seconds or self.config["trader"]["poll_interval_seconds"]
        logger.info("Starting options trading loop for %s every %ds (Ctrl+C to stop)", symbols, interval)
        try:
            while True:
                self.run_once(symbols)
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Options trading loop stopped by user.")
