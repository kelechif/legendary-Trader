from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trading_bot.backtest.engine import BacktestMetrics, compute_performance_metrics
from trading_bot.features.indicators import add_all_indicators, build_feature_matrix
from trading_bot.logger import get_logger
from trading_bot.ml.model import DirectionModel
from trading_bot.options.pricing import bs_price
from trading_bot.options.risk import OptionsRiskManager
from trading_bot.strategy.signals import Signal, SignalGenerator

logger = get_logger(__name__)


@dataclass
class OptionsBacktestResult:
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    metrics: BacktestMetrics
    train_result: object = None


@dataclass
class _OpenOption:
    right: str
    strike: float
    entry_date: object
    expiry_date: object
    iv: float
    contracts: int
    entry_premium: float
    take_profit_premium: float
    stop_loss_premium: float


class SyntheticOptionsBacktester:
    """Approximates a long-calls/long-puts strategy over historical underlying
    data, reusing the same ML direction model and signal generator as the
    equity backtester.

    IMPORTANT LIMITATION: free historical options-chain data (strikes, real
    bid/ask, real implied vol history) isn't available, so contracts here are
    priced with Black-Scholes using trailing realized volatility of the
    underlying as an implied-vol proxy. Treat results as a read on the
    directional signal's quality when expressed through options, not as a
    faithful reproduction of what a real options book would have done.
    """

    def __init__(
        self,
        starting_cash: float = 100_000,
        dte_days: int = 30,
        otm_pct: float = 0.0,
        risk_free_rate: float = 0.04,
        iv_lookback: int = 20,
        annualization_factor: int = 252,
    ):
        self.starting_cash = starting_cash
        self.dte_days = dte_days
        self.otm_pct = otm_pct
        self.risk_free_rate = risk_free_rate
        self.iv_lookback = iv_lookback
        self.annualization_factor = annualization_factor

    def run(
        self,
        raw_df: pd.DataFrame,
        model: DirectionModel,
        signal_generator: SignalGenerator,
        risk_manager: OptionsRiskManager,
    ) -> OptionsBacktestResult:
        train_result = model.train(raw_df)

        enriched = add_all_indicators(raw_df)
        features = build_feature_matrix(enriched)[model.feature_columns]
        valid = features.dropna()

        split_idx = int(len(valid) * model.train_test_split)
        test_index = valid.index[split_idx:]
        if len(test_index) < 2:
            raise ValueError("Not enough out-of-sample bars to run an options backtest.")

        proba_up = model.model.predict_proba(valid.loc[test_index])[:, 1]
        proba_series = pd.Series(proba_up, index=test_index)

        realized_vol = enriched["close"].pct_change().rolling(self.iv_lookback).std() * np.sqrt(
            self.annualization_factor
        )

        cash = self.starting_cash
        position: _OpenOption | None = None
        equity_rows = []
        trades = []

        for date in test_index:
            price = float(enriched.loc[date, "close"])

            if position is not None:
                days_left = (position.expiry_date - date).days
                if days_left <= 0:
                    proceeds, trade = self._settle_at_expiry(position, price, date)
                    cash += proceeds
                    trades.append(trade)
                    position = None
                else:
                    mark = bs_price(price, position.strike, days_left / 365, self.risk_free_rate,
                                     position.iv, position.right)
                    if mark <= position.stop_loss_premium or mark >= position.take_profit_premium:
                        reason = "stop_loss" if mark <= position.stop_loss_premium else "take_profit"
                        proceeds, trade = self._close_at_mark(position, mark, date, reason)
                        cash += proceeds
                        trades.append(trade)
                        position = None

            equity_before_signal = cash + self._mark_value(position, price, date)
            sig = signal_generator.generate(raw_df.loc[:date], float(proba_series.loc[date]))

            if position is None and sig.signal in (Signal.BUY, Signal.SELL):
                right = "call" if sig.signal == Signal.BUY else "put"
                strike = price * (1 + self.otm_pct) if right == "call" else price * (1 - self.otm_pct)
                expiry_date = date + pd.Timedelta(days=self.dte_days)
                iv = realized_vol.loc[date]
                iv = float(iv) if not np.isnan(iv) and iv > 0 else 0.25
                premium = bs_price(price, strike, self.dte_days / 365, self.risk_free_rate, iv, right)

                if premium > 0.01:
                    plan = risk_manager.plan(equity_before_signal, premium)
                    if plan.contracts > 0:
                        cost = plan.contracts * premium * 100
                        if cost <= cash:
                            cash -= cost
                            position = _OpenOption(
                                right=right, strike=strike, entry_date=date, expiry_date=expiry_date,
                                iv=iv, contracts=plan.contracts, entry_premium=premium,
                                take_profit_premium=plan.take_profit_premium,
                                stop_loss_premium=plan.stop_loss_premium,
                            )
            elif position is not None and self._is_opposite_signal(position, sig.signal):
                days_left = max((position.expiry_date - date).days, 0)
                mark = bs_price(price, position.strike, max(days_left, 1) / 365, self.risk_free_rate,
                                 position.iv, position.right)
                proceeds, trade = self._close_at_mark(position, mark, date, "signal_exit")
                cash += proceeds
                trades.append(trade)
                position = None

            equity = cash + self._mark_value(position, price, date)
            equity_rows.append({"date": date, "equity": equity, "cash": cash})

        equity_curve = pd.DataFrame(equity_rows).set_index("date")
        trades_df = pd.DataFrame(trades)
        metrics = compute_performance_metrics(
            equity_curve, trades_df, self.starting_cash, self.annualization_factor
        )

        return OptionsBacktestResult(
            equity_curve=equity_curve, trades=trades_df, metrics=metrics, train_result=train_result
        )

    @staticmethod
    def _is_opposite_signal(position: _OpenOption, signal: Signal) -> bool:
        return (position.right == "call" and signal == Signal.SELL) or (
            position.right == "put" and signal == Signal.BUY
        )

    def _mark_value(self, position: _OpenOption | None, price: float, date) -> float:
        if position is None:
            return 0.0
        days_left = max((position.expiry_date - date).days, 0)
        if days_left <= 0:
            intrinsic = max(price - position.strike, 0.0) if position.right == "call" else max(
                position.strike - price, 0.0
            )
            return intrinsic * 100 * position.contracts
        mark = bs_price(price, position.strike, days_left / 365, self.risk_free_rate, position.iv, position.right)
        return mark * 100 * position.contracts

    @staticmethod
    def _close_at_mark(position: _OpenOption, mark: float, date, reason: str) -> tuple[float, dict]:
        proceeds = mark * 100 * position.contracts
        trade = {
            "entry_date": position.entry_date, "exit_date": date, "right": position.right,
            "strike": position.strike, "contracts": position.contracts,
            "entry_premium": position.entry_premium, "exit_premium": mark,
            "pnl": proceeds - position.entry_premium * 100 * position.contracts, "reason": reason,
        }
        return proceeds, trade

    @staticmethod
    def _settle_at_expiry(position: _OpenOption, price: float, date) -> tuple[float, dict]:
        intrinsic = max(price - position.strike, 0.0) if position.right == "call" else max(
            position.strike - price, 0.0
        )
        return SyntheticOptionsBacktester._close_at_mark(position, intrinsic, date, "expired")
