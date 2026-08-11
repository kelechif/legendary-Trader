from datetime import timedelta

from services.shared.config import CANDLE_HISTORY_LIMIT


def parse_timeframe(tf):
    """Convert '1m', '5m', '15m', '1h' to timedelta."""
    unit = tf[-1]
    value = int(tf[:-1])
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)
    raise ValueError(f"Unknown timeframe: {tf}")


def bucket_timestamp(ts, tf):
    delta = parse_timeframe(tf)
    seconds = int(delta.total_seconds())
    epoch = int(ts.timestamp())
    floored = epoch - (epoch % seconds)
    return ts.fromtimestamp(floored, tz=ts.tzinfo)


def append_candle(history, buf, limit=CANDLE_HISTORY_LIMIT):
    if not buf:
        return
    candle = {
        "open": buf[0],
        "high": max(buf),
        "low": min(buf),
        "close": buf[-1],
    }
    history.append(candle)
    if len(history) > limit:
        history.pop(0)


def forming_candle(buf):
    if not buf:
        return None
    return {
        "open": buf[0],
        "high": max(buf),
        "low": min(buf),
        "close": buf[-1],
        "forming": True,
    }


def candles_with_forming(history, buf):
    result = list(history)
    forming = forming_candle(buf)
    if forming:
        result.append(forming)
    return result
