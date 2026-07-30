import math

from trading_bot.ml.model import DirectionModel
from trading_bot.options.backtest import SyntheticOptionsBacktester
from trading_bot.options.pricing import bs_greeks, bs_price
from trading_bot.options.risk import OptionsRiskManager, OptionsRiskParams
from trading_bot.options.strategy import signal_to_option_intent
from trading_bot.strategy.signals import Signal, SignalGenerator, TradeSignal
from tests.utils import make_synthetic_ohlcv


def test_bs_price_call_put_parity():
    S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.03, 0.25
    call = bs_price(S, K, T, r, sigma, "call")
    put = bs_price(S, K, T, r, sigma, "put")
    # put-call parity: C - P = S - K*exp(-rT)
    assert math.isclose(call - put, S - K * math.exp(-r * T), rel_tol=1e-6, abs_tol=1e-6)


def test_bs_price_deep_itm_call_near_intrinsic():
    price = bs_price(spot=200, strike=50, years_to_expiry=0.01, risk_free_rate=0.03, sigma=0.2, right="call")
    assert price >= 150 - 1  # close to intrinsic value of 150


def test_bs_price_at_expiry_equals_intrinsic():
    call = bs_price(spot=110, strike=100, years_to_expiry=0, risk_free_rate=0.03, sigma=0.2, right="call")
    put = bs_price(spot=90, strike=100, years_to_expiry=0, risk_free_rate=0.03, sigma=0.2, right="put")
    assert call == 10
    assert put == 10


def test_bs_greeks_delta_bounds():
    call_delta = bs_greeks(100, 100, 0.5, 0.03, 0.25, "call")["delta"]
    put_delta = bs_greeks(100, 100, 0.5, 0.03, 0.25, "put")["delta"]
    assert 0 <= call_delta <= 1
    assert -1 <= put_delta <= 0


def test_signal_to_option_intent_maps_directions():
    assert signal_to_option_intent(TradeSignal(Signal.BUY, 0.9, "x")).right == "call"
    assert signal_to_option_intent(TradeSignal(Signal.SELL, 0.1, "x")).right == "put"
    assert signal_to_option_intent(TradeSignal(Signal.HOLD, 0.5, "x")).right is None


def test_options_risk_manager_sizes_within_caps():
    rm = OptionsRiskManager(OptionsRiskParams(risk_per_trade_pct=0.01, max_position_pct=0.10))
    plan = rm.plan(equity=100_000, premium_per_contract=2.5)

    assert plan.contracts > 0
    assert plan.total_cost <= 100_000 * 0.10 + 1e-6
    assert plan.stop_loss_premium < 2.5 < plan.take_profit_premium


def test_options_risk_manager_zero_premium_is_safe():
    rm = OptionsRiskManager(OptionsRiskParams())
    plan = rm.plan(equity=100_000, premium_per_contract=0.0)
    assert plan.contracts == 0


def test_synthetic_options_backtest_runs_end_to_end():
    df = make_synthetic_ohlcv(n=500)

    model = DirectionModel(model_type="random_forest", n_estimators=50, max_depth=4,
                            lookahead_bars=1, up_threshold_pct=0.0, train_test_split=0.8)
    signal_generator = SignalGenerator(min_probability=0.55)
    risk_manager = OptionsRiskManager(OptionsRiskParams())

    engine = SyntheticOptionsBacktester(starting_cash=100_000, dte_days=30)
    result = engine.run(df, model, signal_generator, risk_manager)

    assert len(result.equity_curve) > 0
    assert result.metrics.final_equity > 0
