from __future__ import annotations

import time
from typing import Any

from trading_bot.data.fetcher import DataFetcher
from trading_bot.execution.broker import AlpacaBroker, BaseBroker, PaperBroker
from trading_bot.features.indicators import add_all_indicators
from trading_bot.logger import get_logger
from trading_bot.ml.model import DirectionModel
from trading_bot.strategy.risk import RiskManager, RiskParams
from trading_bot.strategy.signals import Signal, SignalGenerator

logger = get_logger(__name__)


def build_broker(config: dict[str, Any]) -> BaseBroker:
    broker_cfg = config["broker"]
    if broker_cfg.get("mode") == "alpaca":
        return AlpacaBroker(
            api_key=broker_cfg.get("alpaca_api_key"),
            secret_key=broker_cfg.get("alpaca_secret_key"),
            base_url=broker_cfg.get("alpaca_base_url"),
        )
    return PaperBroker(
        starting_cash=config["backtest"]["starting_cash"],
        account_file=broker_cfg.get("account_file", "paper_account.json"),
    )


class TradingBot:
    """Orchestrates one evaluation cycle: fetch data -> ML predict -> generate
    signal -> risk-managed sizing -> submit order to the configured broker.

    Defaults to the PaperBroker so nothing is ever sent to a real market unless
    the operator explicitly sets broker.mode: alpaca and supplies API keys.
    """

    def __init__(self, config: dict[str, Any], broker: BaseBroker | None = None):
        self.config = config
        self.fetcher = DataFetcher()
        self.broker = broker or build_broker(config)
        self.signal_generator = SignalGenerator(min_probability=config["model"]["min_probability"])
        self.risk_manager = RiskManager(RiskParams(**config["risk"]))
        self._models: dict[str, DirectionModel] = {}

    def _get_model(self, symbol: str, raw_df) -> DirectionModel:
        if symbol in self._models:
            return self._models[symbol]
        try:
            model = DirectionModel.load(symbol)
            logger.info("Loaded cached model for %s", symbol)
        except FileNotFoundError:
            model_cfg = self.config["model"]
            model = DirectionModel(
                model_type=model_cfg["type"],
                n_estimators=model_cfg["n_estimators"],
                max_depth=model_cfg["max_depth"],
                lookahead_bars=model_cfg["lookahead_bars"],
                up_threshold_pct=model_cfg["up_threshold_pct"],
                train_test_split=model_cfg["train_test_split"],
            )
            model.train(raw_df)
            model.save(symbol)
        self._models[symbol] = model
        return model

    def evaluate_symbol(self, symbol: str) -> dict[str, Any]:
        data_cfg = self.config["data"]
        raw_df = self.fetcher.fetch(symbol, period=data_cfg["history_period"], interval=data_cfg["interval"])

        model = self._get_model(symbol, raw_df)
        prediction = model.predict_latest(raw_df)
        signal = self.signal_generator.generate(raw_df, prediction["probability_up"])

        latest_close = float(raw_df["close"].iloc[-1])
        latest_atr = float(add_all_indicators(raw_df)["atr_14"].iloc[-1])

        return {
            "symbol": symbol,
            "signal": signal,
            "prediction": prediction,
            "price": latest_close,
            "atr": latest_atr,
        }

    def act_on_evaluation(self, evaluation: dict[str, Any]) -> None:
        symbol = evaluation["symbol"]
        signal = evaluation["signal"]
        price = evaluation["price"]
        atr = evaluation["atr"]

        equity = self.broker.get_equity()
        position = self.broker.get_position(symbol)

        if signal.signal == Signal.BUY and position is None:
            plan = self.risk_manager.plan_long(equity, price, atr)
            if plan.shares > 0:
                self.broker.submit_order(symbol, "BUY", plan.shares, price, plan.stop_loss, plan.take_profit)
            else:
                logger.info("%s: BUY signal but risk-sized shares == 0, skipping", symbol)
        elif signal.signal == Signal.SELL and position is not None:
            self.broker.submit_order(symbol, "SELL", position.shares, price)
        else:
            logger.info("%s: %s (%s) -> no action", symbol, signal.signal.value, signal.reason)

    def run_once(self, symbols: list[str]) -> list[dict[str, Any]]:
        results = []
        for symbol in symbols:
            try:
                evaluation = self.evaluate_symbol(symbol)
                self.act_on_evaluation(evaluation)
                results.append(evaluation)
            except Exception as exc:  # noqa: BLE001 - one bad symbol shouldn't kill the run
                logger.exception("Failed to evaluate %s: %s", symbol, exc)
        return results

    def run_loop(self, symbols: list[str], poll_interval_seconds: int | None = None) -> None:
        interval = poll_interval_seconds or self.config["trader"]["poll_interval_seconds"]
        logger.info("Starting trading loop for %s every %ds (Ctrl+C to stop)", symbols, interval)
        try:
            while True:
                self.run_once(symbols)
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Trading loop stopped by user.")
