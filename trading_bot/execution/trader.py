from __future__ import annotations

import time
from typing import Any

from trading_bot.data.fetcher import DataFetcher
from trading_bot.execution.broker import AlpacaBroker, BaseBroker, MoomooBroker, PaperBroker
from trading_bot.features.indicators import add_all_indicators
from trading_bot.logger import get_logger
from trading_bot.ml.model import DirectionModel, load_or_train_model
from trading_bot.strategy.risk import PositionPlan, RiskManager, RiskParams
from trading_bot.strategy.signals import Signal, SignalGenerator

logger = get_logger(__name__)


def build_broker(config: dict[str, Any]) -> BaseBroker:
    broker_cfg = config["broker"]
    mode = broker_cfg.get("mode")

    if mode == "alpaca":
        return AlpacaBroker(
            api_key=broker_cfg.get("alpaca_api_key"),
            secret_key=broker_cfg.get("alpaca_secret_key"),
            base_url=broker_cfg.get("alpaca_base_url"),
        )
    if mode == "moomoo":
        moomoo_cfg = broker_cfg.get("moomoo", {})
        return MoomooBroker(
            host=moomoo_cfg.get("host", "127.0.0.1"),
            port=moomoo_cfg.get("port", 11111),
            trd_env=moomoo_cfg.get("trd_env", "SIMULATE"),
            market=moomoo_cfg.get("market", "US"),
            code_prefix=moomoo_cfg.get("code_prefix", "US."),
            acc_id=moomoo_cfg.get("acc_id"),
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
        if symbol not in self._models:
            self._models[symbol] = load_or_train_model(symbol, raw_df, self.config["model"])
        return self._models[symbol]

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

    def plan_for_evaluation(self, evaluation: dict[str, Any]) -> PositionPlan | None:
        """Preview the risk-managed entry/stop/target for a BUY signal without
        submitting an order. Returns None for SELL/HOLD, where there's no new
        long entry to plan (this bot is long-only; SELL just closes an existing
        position at market)."""
        if evaluation["signal"].signal != Signal.BUY:
            return None
        equity = self.broker.get_equity()
        return self.risk_manager.plan_long(equity, evaluation["price"], evaluation["atr"])

    def submit_plan(self, symbol: str, price: float, plan: PositionPlan):
        """Execute the exact BUY plan a caller previously previewed via
        plan_for_evaluation, so a one-click UI trades on the numbers it showed
        the user rather than silently re-pricing at click time."""
        return self.broker.submit_order(symbol, "BUY", plan.shares, price, plan.stop_loss, plan.take_profit)

    def check_exits(self) -> list[dict[str, Any]]:
        """Re-price every open position against its stored stop-loss/take-profit
        and close (at that trigger price) any that have been breached.

        This is the piece that makes the stop/target shown at entry mean
        something after the fact — nothing else in this bot watches positions
        between evaluation cycles. PaperBroker fills the close immediately;
        live brokers don't get automatic bracket monitoring here, so this is a
        no-op for anything other than a PaperBroker position (open positions on
        a live broker should be protected by real bracket/stop orders placed at
        the broker, which this project does not yet submit).
        """
        closed = []
        if not isinstance(self.broker, PaperBroker):
            return closed

        for symbol, position in list(self.broker.positions.items()):
            try:
                raw_df = self.fetcher.fetch(symbol, period="5d", interval="1d")
            except Exception as exc:  # noqa: BLE001 - one bad symbol shouldn't block the rest
                logger.warning("check_exits: could not re-price %s: %s", symbol, exc)
                continue

            price = float(raw_df["close"].iloc[-1])
            trigger_price, reason = None, None
            if price <= position.stop_loss:
                trigger_price, reason = position.stop_loss, "stop_loss"
            elif price >= position.take_profit:
                trigger_price, reason = position.take_profit, "take_profit"

            if trigger_price is not None:
                result = self.broker.submit_order(symbol, "SELL", position.shares, trigger_price)
                closed.append({"symbol": symbol, "reason": reason, "price": trigger_price, "result": result})
        return closed

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
