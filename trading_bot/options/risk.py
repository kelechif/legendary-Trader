from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OptionsRiskParams:
    risk_per_trade_pct: float = 0.01
    max_position_pct: float = 0.10
    take_profit_pct: float = 0.75
    stop_loss_pct: float = 0.50


@dataclass
class OptionsPositionPlan:
    contracts: int
    premium_per_contract: float
    take_profit_premium: float
    stop_loss_premium: float
    total_cost: float


class OptionsRiskManager:
    """Sizes long option positions off premium at risk. For a long call/put the
    maximum loss is the premium paid, so risk-based sizing is a direct function
    of contract cost rather than a stop-loss distance.
    """

    def __init__(self, params: OptionsRiskParams):
        self.params = params

    def plan(self, equity: float, premium_per_contract: float) -> OptionsPositionPlan:
        if equity <= 0 or premium_per_contract <= 0:
            return OptionsPositionPlan(0, premium_per_contract, 0.0, 0.0, 0.0)

        cost_per_contract = premium_per_contract * 100
        contracts_by_risk = (equity * self.params.risk_per_trade_pct) / cost_per_contract
        contracts_by_cap = (equity * self.params.max_position_pct) / cost_per_contract
        contracts = int(max(0, min(contracts_by_risk, contracts_by_cap)))

        return OptionsPositionPlan(
            contracts=contracts,
            premium_per_contract=premium_per_contract,
            take_profit_premium=round(premium_per_contract * (1 + self.params.take_profit_pct), 4),
            stop_loss_premium=round(premium_per_contract * (1 - self.params.stop_loss_pct), 4),
            total_cost=round(contracts * cost_per_contract, 2),
        )
