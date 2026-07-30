from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from trading_bot.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Position:
    symbol: str
    shares: int
    entry_price: float
    stop_loss: float
    take_profit: float


@dataclass
class OrderResult:
    symbol: str
    side: str
    shares: int
    price: float
    timestamp: str
    status: str
    reason: str = ""


@dataclass
class OptionPosition:
    contract_symbol: str
    underlying: str
    right: str  # "call" | "put"
    strike: float
    expiration: str
    contracts: int
    entry_premium: float


@dataclass
class OptionOrderResult:
    contract_symbol: str
    underlying: str
    side: str  # "BUY_TO_OPEN" | "SELL_TO_CLOSE"
    contracts: int
    premium: float
    timestamp: str
    status: str
    reason: str = ""


class BaseBroker(ABC):
    @abstractmethod
    def get_equity(self) -> float: ...

    @abstractmethod
    def get_position(self, symbol: str) -> Position | None: ...

    @abstractmethod
    def submit_order(self, symbol: str, side: str, shares: int, price: float,
                      stop_loss: float = 0.0, take_profit: float = 0.0) -> OrderResult: ...


class PaperBroker(BaseBroker):
    """Simulated broker: fills instantly at the supplied price and persists
    account state (cash, positions, trade log) to a local JSON file. No real
    orders are ever sent anywhere — this is the default, safe mode.
    """

    def __init__(self, starting_cash: float = 100_000, account_file: str = "paper_account.json"):
        self.account_file = Path(account_file)
        self.cash = starting_cash
        self.positions: dict[str, Position] = {}
        self.trade_log: list[dict] = []
        self.option_positions: dict[str, OptionPosition] = {}
        self.option_trade_log: list[dict] = []
        self._load()

    def _load(self) -> None:
        if not self.account_file.exists():
            return
        data = json.loads(self.account_file.read_text())
        self.cash = data["cash"]
        self.positions = {s: Position(**p) for s, p in data["positions"].items()}
        self.trade_log = data["trade_log"]
        self.option_positions = {
            s: OptionPosition(**p) for s, p in data.get("option_positions", {}).items()
        }
        self.option_trade_log = data.get("option_trade_log", [])

    def _save(self) -> None:
        payload = {
            "cash": self.cash,
            "positions": {s: asdict(p) for s, p in self.positions.items()},
            "trade_log": self.trade_log,
            "option_positions": {s: asdict(p) for s, p in self.option_positions.items()},
            "option_trade_log": self.option_trade_log,
        }
        self.account_file.write_text(json.dumps(payload, indent=2))

    def get_equity(self, mark_prices: dict[str, float] | None = None,
                    option_mark_premiums: dict[str, float] | None = None) -> float:
        equity = self.cash
        mark_prices = mark_prices or {}
        for symbol, pos in self.positions.items():
            price = mark_prices.get(symbol, pos.entry_price)
            equity += pos.shares * price

        option_mark_premiums = option_mark_premiums or {}
        for contract_symbol, pos in self.option_positions.items():
            premium = option_mark_premiums.get(contract_symbol, pos.entry_premium)
            equity += pos.contracts * premium * 100
        return equity

    def get_position(self, symbol: str) -> Position | None:
        return self.positions.get(symbol)

    def get_option_position(self, contract_symbol: str) -> OptionPosition | None:
        return self.option_positions.get(contract_symbol)

    def find_option_position_for_underlying(self, underlying: str) -> OptionPosition | None:
        for pos in self.option_positions.values():
            if pos.underlying == underlying:
                return pos
        return None

    def submit_option_order(self, contract_symbol: str, underlying: str, right: str, strike: float,
                             expiration: str, contracts: int, premium: float, side: str) -> OptionOrderResult:
        timestamp = datetime.now(timezone.utc).isoformat()

        if contracts <= 0:
            return OptionOrderResult(contract_symbol, underlying, side, contracts, premium, timestamp,
                                      "rejected", "non-positive contract count")

        if side.upper() == "BUY_TO_OPEN":
            cost = contracts * premium * 100
            if cost > self.cash:
                return OptionOrderResult(contract_symbol, underlying, side, contracts, premium, timestamp,
                                          "rejected", "insufficient cash")
            self.cash -= cost
            self.option_positions[contract_symbol] = OptionPosition(
                contract_symbol, underlying, right, strike, expiration, contracts, premium
            )
            status, reason = "filled", ""
        elif side.upper() == "SELL_TO_CLOSE":
            pos = self.option_positions.get(contract_symbol)
            if pos is None or pos.contracts < contracts:
                return OptionOrderResult(contract_symbol, underlying, side, contracts, premium, timestamp,
                                          "rejected", "no matching position")
            self.cash += contracts * premium * 100
            if pos.contracts == contracts:
                del self.option_positions[contract_symbol]
            else:
                pos.contracts -= contracts
            status, reason = "filled", ""
        else:
            return OptionOrderResult(contract_symbol, underlying, side, contracts, premium, timestamp,
                                      "rejected", f"unknown side {side}")

        result = OptionOrderResult(contract_symbol, underlying, side, contracts, premium, timestamp, status, reason)
        self.option_trade_log.append(asdict(result))
        self._save()
        logger.info("Paper option order filled: %s %s %s x%d @ %.2f", side, contract_symbol, right, contracts, premium)
        return result

    def submit_order(self, symbol: str, side: str, shares: int, price: float,
                      stop_loss: float = 0.0, take_profit: float = 0.0) -> OrderResult:
        timestamp = datetime.now(timezone.utc).isoformat()

        if shares <= 0:
            return OrderResult(symbol, side, shares, price, timestamp, "rejected", "non-positive share count")

        if side.upper() == "BUY":
            cost = shares * price
            if cost > self.cash:
                return OrderResult(symbol, side, shares, price, timestamp, "rejected", "insufficient cash")
            self.cash -= cost
            self.positions[symbol] = Position(symbol, shares, price, stop_loss, take_profit)
            status, reason = "filled", ""
        elif side.upper() == "SELL":
            pos = self.positions.get(symbol)
            if pos is None or pos.shares < shares:
                return OrderResult(symbol, side, shares, price, timestamp, "rejected", "no matching position")
            self.cash += shares * price
            if pos.shares == shares:
                del self.positions[symbol]
            else:
                pos.shares -= shares
            status, reason = "filled", ""
        else:
            return OrderResult(symbol, side, shares, price, timestamp, "rejected", f"unknown side {side}")

        result = OrderResult(symbol, side, shares, price, timestamp, status, reason)
        self.trade_log.append(asdict(result))
        self._save()
        logger.info("Paper order filled: %s %s %d @ %.2f", side, symbol, shares, price)
        return result


class AlpacaBroker(BaseBroker):
    """Optional real-money/live-paper broker via Alpaca. Only imported/instantiated
    if broker.mode == "alpaca" and API keys are configured — disabled by default.
    """

    def __init__(self, api_key: str, secret_key: str, base_url: str):
        try:
            import alpaca_trade_api as tradeapi
        except ImportError as exc:
            raise ImportError(
                "AlpacaBroker requires the 'alpaca-trade-api' package: pip install alpaca-trade-api"
            ) from exc

        if not api_key or not secret_key:
            raise ValueError("Alpaca API key/secret are required to use AlpacaBroker.")

        self.api = tradeapi.REST(api_key, secret_key, base_url)

    def get_equity(self) -> float:
        return float(self.api.get_account().equity)

    def get_position(self, symbol: str) -> Position | None:
        try:
            p = self.api.get_position(symbol)
        except Exception:
            return None
        return Position(symbol, int(float(p.qty)), float(p.avg_entry_price), 0.0, 0.0)

    def submit_order(self, symbol: str, side: str, shares: int, price: float,
                      stop_loss: float = 0.0, take_profit: float = 0.0) -> OrderResult:
        timestamp = datetime.now(timezone.utc).isoformat()
        order = self.api.submit_order(
            symbol=symbol, qty=shares, side=side.lower(), type="market", time_in_force="day"
        )
        logger.warning("LIVE order submitted via Alpaca: %s %s %d", side, symbol, shares)
        return OrderResult(symbol, side, shares, price, timestamp, order.status)
