from trading_bot.features.indicators import add_all_indicators, build_feature_matrix, rsi
from tests.utils import make_synthetic_ohlcv


def test_add_all_indicators_columns_present():
    df = make_synthetic_ohlcv()
    enriched = add_all_indicators(df)

    expected_cols = {
        "sma_20", "sma_50", "sma_200", "ema_12", "ema_26", "rsi_14",
        "macd", "macd_signal", "macd_hist", "bb_upper", "bb_mid", "bb_lower",
        "bb_pct_b", "atr_14", "atr_pct", "obv", "volatility_20", "return_1",
    }
    assert expected_cols.issubset(enriched.columns)
    assert len(enriched) == len(df)


def test_rsi_bounds():
    df = make_synthetic_ohlcv()
    values = rsi(df["close"]).dropna()
    assert (values >= 0).all() and (values <= 100).all()


def test_build_feature_matrix_no_lookahead_columns():
    df = make_synthetic_ohlcv()
    enriched = add_all_indicators(df)
    features = build_feature_matrix(enriched)

    assert len(features) == len(df)
    # last row should be computable (only depends on past bars)
    assert not features.iloc[-1].isna().all()
