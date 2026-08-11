"""Market regime classification for daily equity strategies."""

from services.strategy_engine.plugins.institutional_trend import _regime_ok, _valid


def classify_regime(candle: dict, params: dict | None = None) -> str:
    """
    Classify daily regime:
    - BULL: full institutional trend regime (MA stack + RSI band + MACD)
    - BEAR: below 200 SMA with death cross structure
    - SIDEWAYS: everything else
    """
    params = params or {}
    if _regime_ok(candle, params):
        return "BULL"

    if not _valid(candle, "close", "sma200", "sma50"):
        return "SIDEWAYS"

    if candle["close"] < candle["sma200"] and candle["sma50"] < candle["sma200"]:
        return "BEAR"

    return "SIDEWAYS"


def entry_allowed(regime: str, cfg: dict | None = None) -> bool:
    cfg = cfg or {}
    allowed = cfg.get("entry_allowed", ["BULL"])
    if cfg.get("block_bear_entries", True) and regime == "BEAR":
        return False
    return regime in allowed
