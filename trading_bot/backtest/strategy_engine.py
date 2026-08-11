from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trading_bot.backtest.engine import BacktestResult, compute_performance_metrics
from trading_bot.features.indicators import add_all_indicators
from trading_bot.logger import get_logger
from trading_bot.strategy.risk import RiskManager
from trading_bot.strategy.rules import RuleStrategy
from trading_bot.strategy.signals import Signal

logger = get_logger(__name__)


@dataclass
class _OpenPosition:
    shares: int
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_date: object


class RuleBacktester:
    """Walk-forward, long-only backtest for indicator-only strategies (no ML
    training involved). Same position sizing, ATR stop/target, and exit
    mechanics as `BacktestEngine`, but driven by a `RuleStrategy`'s per-bar
    signal instead of a trained model's prediction.

    Trades only the same held-out tail fraction of history (`test_split`) as
    `BacktestEngine` does by default, so a rule strategy and the ML strategy
    can be compared over an identical window rather than different ones.
    """

    def __init__(
        self,
        starting_cash: float = 100_000,
        commission_per_share: float = 0.0,
        slippage_pct: float = 0.0005,
        test_split: float = 0.8,
        annualization_factor: int = 252,
    ):
        self.starting_cash = starting_cash
        self.commission_per_share = commission_per_share
        self.slippage_pct = slippage_pct
        self.test_split = test_split
        self.annualization_factor = annualization_factor

    def run(self, raw_df: pd.DataFrame, strategy: RuleStrategy, risk_manager: RiskManager) -> BacktestResult:
        enriched = add_all_indicators(raw_df).dropna(subset=["sma_200", "rsi_14", "atr_14"])
        if len(enriched) < 10:
            raise ValueError("Not enough history after indicator warmup to run a backtest.")

        split_idx = int(len(enriched) * self.test_split)
        test_index = enriched.index[split_idx:]
        if len(test_index) < 2:
            raise ValueError("Not enough out-of-sample bars to run a backtest.")

        cash = self.starting_cash
        position: _OpenPosition | None = None
        equity_rows = []
        trades = []

        for date in test_index:
            row = enriched.loc[date]
            price_high, price_low, price_close = row["high"], row["low"], row["close"]

            if position is not None:
                exit_price, exit_reason = None, None
                if price_low <= position.stop_loss:
                    exit_price, exit_reason = position.stop_loss, "stop_loss"
                elif price_high >= position.take_profit:
                    exit_price, exit_reason = position.take_profit, "take_profit"

                if exit_price is not None:
                    proceeds = exit_price * position.shares * (1 - self.slippage_pct)
                    proceeds -= self.commission_per_share * position.shares
                    cash += proceeds
                    trades.append({
                        "entry_date": position.entry_date, "exit_date": date, "shares": position.shares,
                        "entry_price": position.entry_price, "exit_price": exit_price,
                        "pnl": proceeds - position.entry_price * position.shares, "reason": exit_reason,
                    })
                    position = None

            equity_before_signal = cash + (position.shares * price_close if position else 0)
            sig = strategy.signal(row)

            if position is None and sig.signal == Signal.BUY and not np.isnan(row["atr_14"]):
                plan = risk_manager.plan_long(equity_before_signal, price_close, row["atr_14"])
                if plan.shares > 0:
                    cost = price_close * plan.shares * (1 + self.slippage_pct)
                    cost += self.commission_per_share * plan.shares
                    if cost <= cash:
                        cash -= cost
                        position = _OpenPosition(
                            shares=plan.shares, entry_price=price_close, stop_loss=plan.stop_loss,
                            take_profit=plan.take_profit, entry_date=date,
                        )
            elif position is not None and sig.signal == Signal.SELL:
                proceeds = price_close * position.shares * (1 - self.slippage_pct)
                proceeds -= self.commission_per_share * position.shares
                cash += proceeds
                trades.append({
                    "entry_date": position.entry_date, "exit_date": date, "shares": position.shares,
                    "entry_price": position.entry_price, "exit_price": price_close,
                    "pnl": proceeds - position.entry_price * position.shares, "reason": "signal_exit",
                })
                position = None

            equity = cash + (position.shares * price_close if position else 0)
            equity_rows.append({"date": date, "equity": equity, "cash": cash,
                                 "position_shares": position.shares if position else 0})

        equity_curve = pd.DataFrame(equity_rows).set_index("date")
        trades_df = pd.DataFrame(trades)
        metrics = compute_performance_metrics(equity_curve, trades_df, self.starting_cash, self.annualization_factor)

        return BacktestResult(equity_curve=equity_curve, trades=trades_df, metrics=metrics, train_result=None)
