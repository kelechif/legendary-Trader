from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskParams:
    risk_per_trade_pct: float = 0.01
    stop_loss_atr_mult: float = 2.0
    take_profit_atr_mult: float = 3.0
    max_position_pct: float = 0.25
    max_open_positions: int = 5
    daily_loss_limit_pct: float = 0.03


@dataclass
class PositionPlan:
    shares: int
    stop_loss: float
    take_profit: float
    dollar_risk: float


class RiskManager:
    """Volatility-adjusted position sizing and stop/target placement."""

    def __init__(self, params: RiskParams):
        self.params = params

    def plan_long(self, equity: float, entry_price: float, atr: float) -> PositionPlan:
        return self._plan(equity, entry_price, atr, direction=1)

    def plan_short(self, equity: float, entry_price: float, atr: float) -> PositionPlan:
        return self._plan(equity, entry_price, atr, direction=-1)

    def _plan(self, equity: float, entry_price: float, atr: float, direction: int) -> PositionPlan:
        if entry_price <= 0 or atr <= 0 or equity <= 0:
            return PositionPlan(shares=0, stop_loss=entry_price, take_profit=entry_price, dollar_risk=0.0)

        stop_distance = atr * self.params.stop_loss_atr_mult
        target_distance = atr * self.params.take_profit_atr_mult

        dollar_risk = equity * self.params.risk_per_trade_pct
        shares_by_risk = dollar_risk / stop_distance

        max_position_value = equity * self.params.max_position_pct
        shares_by_cap = max_position_value / entry_price

        shares = int(max(0, min(shares_by_risk, shares_by_cap)))

        stop_loss = entry_price - direction * stop_distance
        take_profit = entry_price + direction * target_distance

        return PositionPlan(
            shares=shares,
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            dollar_risk=round(shares * stop_distance, 2),
        )

    def daily_loss_breached(self, equity_start_of_day: float, equity_now: float) -> bool:
        if equity_start_of_day <= 0:
            return False
        drawdown = (equity_start_of_day - equity_now) / equity_start_of_day
        return drawdown >= self.params.daily_loss_limit_pct
