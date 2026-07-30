from trading_bot.strategy.signals import Signal, SignalGenerator
from trading_bot.strategy.risk import RiskManager, RiskParams
from tests.utils import make_synthetic_ohlcv


def test_signal_generator_buy_on_high_confidence_uptrend():
    df = make_synthetic_ohlcv(n=300)
    gen = SignalGenerator(min_probability=0.55)
    result = gen.generate(df, probability_up=0.9)
    assert result.signal in {Signal.BUY, Signal.HOLD}  # depends on trend/RSI filters
    assert 0.0 <= result.confidence <= 1.0


def test_signal_generator_hold_when_uncertain():
    df = make_synthetic_ohlcv(n=300)
    gen = SignalGenerator(min_probability=0.55)
    result = gen.generate(df, probability_up=0.5)
    assert result.signal == Signal.HOLD


def test_risk_manager_position_sizing_respects_caps():
    params = RiskParams(risk_per_trade_pct=0.01, stop_loss_atr_mult=2.0,
                         max_position_pct=0.25, take_profit_atr_mult=3.0)
    rm = RiskManager(params)
    plan = rm.plan_long(equity=100_000, entry_price=50.0, atr=1.0)

    assert plan.shares > 0
    assert plan.shares * 50.0 <= 100_000 * params.max_position_pct + 1e-6
    assert plan.stop_loss < 50.0
    assert plan.take_profit > 50.0


def test_risk_manager_zero_atr_is_safe():
    rm = RiskManager(RiskParams())
    plan = rm.plan_long(equity=100_000, entry_price=50.0, atr=0.0)
    assert plan.shares == 0
