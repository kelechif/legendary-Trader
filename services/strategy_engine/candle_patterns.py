"""Bullish rejection candle patterns for daily pullback entries."""


def is_bullish_rejection(current: dict, previous: dict | None) -> bool:
    if not current or not previous:
        return False

    o = current.get("open")
    h = current.get("high")
    l = current.get("low")
    c = current.get("close")
    prev_o = previous.get("open")
    prev_c = previous.get("close")

    if None in (o, h, l, c, prev_o, prev_c):
        return False

    body = abs(c - o)
    candle_range = h - l
    if candle_range <= 0:
        return False

    lower_wick = (min(o, c) - l)
    hammer = lower_wick > 0.5 * candle_range and body < 0.3 * candle_range
    engulfing = c > o and o < prev_c and c > prev_o
    return hammer or engulfing
