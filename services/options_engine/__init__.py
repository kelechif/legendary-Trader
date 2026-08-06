"""0DTE options research: chain math, P&L simulation, backtest, Moomoo execution."""

from services.options_engine.chain import pick_vertical_strikes, expected_move
from services.options_engine.pnl import simulate_vertical_settle, simulate_fly_settle
from services.options_engine.backtest import run_regime_backtest
from services.options_engine.backtest_realistic import run_realistic_backtest
from services.options_engine.zero_dte_executor import execute_0dte_signal, session_status

__all__ = [
    "pick_vertical_strikes",
    "expected_move",
    "simulate_vertical_settle",
    "simulate_fly_settle",
    "run_regime_backtest",
    "run_realistic_backtest",
    "execute_0dte_signal",
    "session_status",
]
