from trading_bot.backtest.engine import BacktestEngine
from trading_bot.ml.model import DirectionModel
from trading_bot.strategy.risk import RiskManager, RiskParams
from trading_bot.strategy.signals import SignalGenerator
from tests.utils import make_synthetic_ohlcv


def test_backtest_engine_runs_end_to_end():
    df = make_synthetic_ohlcv(n=500)

    model = DirectionModel(model_type="random_forest", n_estimators=50, max_depth=4,
                            lookahead_bars=1, up_threshold_pct=0.0, train_test_split=0.8)
    signal_generator = SignalGenerator(min_probability=0.55)
    risk_manager = RiskManager(RiskParams())

    engine = BacktestEngine(starting_cash=100_000)
    result = engine.run(df, model, signal_generator, risk_manager)

    assert len(result.equity_curve) > 0
    assert result.metrics.final_equity > 0
    assert isinstance(result.metrics.num_trades, int)


def test_backtest_metrics_reasonable_ranges():
    df = make_synthetic_ohlcv(n=500, seed=3)
    model = DirectionModel(n_estimators=50, max_depth=4, train_test_split=0.8)
    engine = BacktestEngine(starting_cash=50_000)

    result = engine.run(df, model, SignalGenerator(min_probability=0.55), RiskManager(RiskParams()))

    assert -100 <= result.metrics.max_drawdown_pct <= 0
    assert result.metrics.win_rate_pct >= 0
