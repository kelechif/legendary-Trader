from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from trading_bot.features.indicators import add_all_indicators, build_feature_matrix
from trading_bot.logger import get_logger
from trading_bot.ml.model import DirectionModel
from trading_bot.strategy.risk import RiskManager, RiskParams
from trading_bot.strategy.signals import Signal, SignalGenerator

logger = get_logger(__name__)


@dataclass
class BacktestMetrics:
    total_return_pct: float
    cagr_pct: float
    annualized_volatility_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    num_trades: int
    final_equity: float


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    metrics: BacktestMetrics
    train_result: object = None


@dataclass
class _OpenPosition:
    shares: int
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_date: object


def compute_performance_metrics(
    equity_curve: pd.DataFrame, trades: pd.DataFrame, starting_cash: float,
    annualization_factor: int = 252,
) -> BacktestMetrics:
    """Shared equity-curve -> performance-metrics calculation, reused by both
    the equity and the synthetic options backtest engines."""
    equity = equity_curve["equity"]
    final_equity = float(equity.iloc[-1])
    total_return = final_equity / starting_cash - 1

    n_bars = len(equity)
    years = max(n_bars / annualization_factor, 1e-9)
    cagr = (final_equity / starting_cash) ** (1 / years) - 1 if final_equity > 0 else -1.0

    daily_returns = equity.pct_change().dropna()
    vol = daily_returns.std() * np.sqrt(annualization_factor) if len(daily_returns) else 0.0
    sharpe = (daily_returns.mean() * annualization_factor) / vol if vol > 1e-12 else 0.0

    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0

    win_rate = float((trades["pnl"] > 0).mean()) if len(trades) else 0.0

    return BacktestMetrics(
        total_return_pct=round(total_return * 100, 2),
        cagr_pct=round(cagr * 100, 2),
        annualized_volatility_pct=round(vol * 100, 2),
        sharpe_ratio=round(float(sharpe), 2),
        max_drawdown_pct=round(max_drawdown * 100, 2),
        win_rate_pct=round(win_rate * 100, 2),
        num_trades=len(trades),
        final_equity=round(final_equity, 2),
    )


class BacktestEngine:
    """Walk-forward, long-only backtest: train the model on the first slice of
    history, then simulate the ML+risk strategy bar-by-bar on the held-out slice.
    """

    def __init__(
        self,
        starting_cash: float = 100_000,
        commission_per_share: float = 0.0,
        slippage_pct: float = 0.0005,
        annualization_factor: int = 252,
    ):
        self.starting_cash = starting_cash
        self.commission_per_share = commission_per_share
        self.slippage_pct = slippage_pct
        self.annualization_factor = annualization_factor

    def run(
        self,
        raw_df: pd.DataFrame,
        model: DirectionModel,
        signal_generator: SignalGenerator,
        risk_manager: RiskManager,
    ) -> BacktestResult:
        train_result = model.train(raw_df)

        enriched = add_all_indicators(raw_df)
        features = build_feature_matrix(enriched)[model.feature_columns]
        valid = features.dropna()

        split_idx = int(len(features.dropna()) * model.train_test_split)
        test_index = valid.index[split_idx:]
        if len(test_index) < 2:
            raise ValueError("Not enough out-of-sample bars to run a backtest.")

        proba_up = model.model.predict_proba(valid.loc[test_index])[:, 1]
        proba_series = pd.Series(proba_up, index=test_index)

        cash = self.starting_cash
        position: _OpenPosition | None = None
        equity_rows = []
        trades = []

        for date in test_index:
            row = enriched.loc[date]
            price_open, price_high, price_low, price_close = (
                row["open"], row["high"], row["low"], row["close"]
            )

            if position is not None:
                exit_price = None
                exit_reason = None
                if price_low <= position.stop_loss:
                    exit_price, exit_reason = position.stop_loss, "stop_loss"
                elif price_high >= position.take_profit:
                    exit_price, exit_reason = position.take_profit, "take_profit"

                if exit_price is not None:
                    proceeds = exit_price * position.shares * (1 - self.slippage_pct)
                    proceeds -= self.commission_per_share * position.shares
                    cash += proceeds
                    trades.append({
                        "entry_date": position.entry_date,
                        "exit_date": date,
                        "shares": position.shares,
                        "entry_price": position.entry_price,
                        "exit_price": exit_price,
                        "pnl": proceeds - position.entry_price * position.shares,
                        "reason": exit_reason,
                    })
                    position = None

            equity_before_signal = cash + (position.shares * price_close if position else 0)

            history_atr = row["atr_14"]
            history_slice = raw_df.loc[:date]
            sig = signal_generator.generate(history_slice, float(proba_series.loc[date]))

            if position is None and sig.signal == Signal.BUY and not np.isnan(history_atr):
                plan = risk_manager.plan_long(equity_before_signal, price_close, history_atr)
                if plan.shares > 0:
                    cost = price_close * plan.shares * (1 + self.slippage_pct)
                    cost += self.commission_per_share * plan.shares
                    if cost <= cash:
                        cash -= cost
                        position = _OpenPosition(
                            shares=plan.shares,
                            entry_price=price_close,
                            stop_loss=plan.stop_loss,
                            take_profit=plan.take_profit,
                            entry_date=date,
                        )
            elif position is not None and sig.signal == Signal.SELL:
                proceeds = price_close * position.shares * (1 - self.slippage_pct)
                proceeds -= self.commission_per_share * position.shares
                cash += proceeds
                trades.append({
                    "entry_date": position.entry_date,
                    "exit_date": date,
                    "shares": position.shares,
                    "entry_price": position.entry_price,
                    "exit_price": price_close,
                    "pnl": proceeds - position.entry_price * position.shares,
                    "reason": "signal_exit",
                })
                position = None

            equity = cash + (position.shares * price_close if position else 0)
            equity_rows.append({"date": date, "equity": equity, "cash": cash,
                                 "position_shares": position.shares if position else 0})

        equity_curve = pd.DataFrame(equity_rows).set_index("date")
        trades_df = pd.DataFrame(trades)
        metrics = self._compute_metrics(equity_curve, trades_df)

        return BacktestResult(
            equity_curve=equity_curve, trades=trades_df, metrics=metrics, train_result=train_result
        )

    def _compute_metrics(self, equity_curve: pd.DataFrame, trades: pd.DataFrame) -> BacktestMetrics:
        return compute_performance_metrics(
            equity_curve, trades, self.starting_cash, self.annualization_factor
        )

    @staticmethod
    def plot_equity_curve(result: BacktestResult, output_path: str) -> None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 5))
        result.equity_curve["equity"].plot(ax=ax)
        ax.set_title("Backtest Equity Curve")
        ax.set_ylabel("Equity ($)")
        ax.set_xlabel("Date")
        fig.tight_layout()
        fig.savefig(output_path)
        plt.close(fig)
