import time

from services.execution_engine.performance import compute_metrics
from services.strategy_engine import choose_signal


def _apply_costs(entry_price, exit_price, position_value, slippage_bps=5, commission=1.0):
    slip = slippage_bps / 10_000
    effective_entry = entry_price * (1 + slip)
    effective_exit = exit_price * (1 - slip)
    gross = (effective_exit - effective_entry) / effective_entry * position_value
    return gross - commission


def run_backtest(prices, strategy_name, params=None, initial_equity=10000.0):
    """Simulate strategy on a flat price series (crypto tick mode)."""
    if len(prices) < 10:
        return {"error": "Need at least 10 price points"}

    equity = initial_equity
    equity_curve = [equity]
    trades = []
    position = 0

    for i in range(len(prices)):
        window = prices[: i + 1]
        signal = choose_signal(strategy_name, window, params)
        price = prices[i]

        if i > 0 and position != 0:
            prev = prices[i - 1]
            if position == 1:
                equity += price - prev
            else:
                equity += prev - price

        if signal == "BUY" and position <= 0:
            position = 1
            trades.append({"index": i, "action": "BUY", "price": price, "time": i})
        elif signal == "SELL" and position >= 0:
            position = -1
            trades.append({"index": i, "action": "SELL", "price": price, "time": i})

        equity_curve.append(equity)

    metrics = compute_metrics(equity_curve, trades, periods_per_year=252 * 24 * 30)
    return {
        "strategy": strategy_name,
        "params": params or {},
        "equity_curve": equity_curve,
        "trades": trades,
        "metrics": metrics,
        "data_points": len(prices),
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def run_backtest_daily(
    candles,
    strategy_name,
    ticker="ASSET",
    params=None,
    initial_equity=100000.0,
    max_positions=10,
    slippage_bps=5,
    commission=1.0,
):
    """Long-only daily OHLCV backtest with ATR stops and equal-weight sizing."""
    if len(candles) < 220:
        return {"error": "Need at least 220 daily bars for indicator warmup"}

    annotated = []
    for c in candles:
        row = dict(c)
        row["ticker"] = ticker
        annotated.append(row)

    cash = initial_equity
    positions = {}
    entry_prices = {}
    equity_curve = [initial_equity]
    trades = []
    stops = {}

    for i in range(1, len(annotated)):
        window = annotated[: i + 1]
        current = window[-1]
        price = current.get("close")
        if price is None:
            equity_curve.append(_portfolio_value(cash, positions, price or 0))
            continue

        # Intrabar stops
        if ticker in positions and stops.get(ticker) is not None:
            stop = stops[ticker]
            if current.get("low") is not None and current["low"] <= stop:
                qty = positions.pop(ticker)
                entry = entry_prices.pop(ticker)
                pos_val = qty * entry
                pnl = _apply_costs(entry, stop, pos_val, slippage_bps, commission)
                cash += qty * stop - commission
                trades.append(
                    {
                        "index": i,
                        "action": "STOP",
                        "price": stop,
                        "shares": qty,
                        "pnl": round(pnl, 2),
                        "date": current.get("date"),
                    }
                )
                stops.pop(ticker, None)

        signal = choose_signal(strategy_name, [], params, window)

        if signal == "SELL" and ticker in positions:
            qty = positions.pop(ticker)
            entry = entry_prices.pop(ticker)
            pos_val = qty * entry
            pnl = _apply_costs(entry, price, pos_val, slippage_bps, commission)
            cash += qty * price - commission
            trades.append(
                {
                    "index": i,
                    "action": "SELL",
                    "price": price,
                    "shares": qty,
                    "pnl": round(pnl, 2),
                    "date": current.get("date"),
                }
            )
            stops.pop(ticker, None)

        if signal == "BUY" and ticker not in positions and len(positions) < max_positions:
            nav = _portfolio_value(cash, positions, price)
            slot_value = nav / max(max_positions, 1)
            qty = int(slot_value / price) if price > 0 else 0
            cost = qty * price + commission
            if qty > 0 and cost <= cash:
                cash -= cost
                positions[ticker] = qty
                entry_prices[ticker] = price
                stops[ticker] = _compute_stop(current)
                trades.append(
                    {
                        "index": i,
                        "action": "BUY",
                        "price": price,
                        "shares": qty,
                        "stop": stops[ticker],
                        "date": current.get("date"),
                    }
                )

        equity_curve.append(_portfolio_value(cash, positions, price))

    metrics = compute_metrics(equity_curve, trades, periods_per_year=252)
    return {
        "strategy": strategy_name,
        "params": params or {},
        "equity_curve": equity_curve,
        "trades": trades,
        "metrics": metrics,
        "data_points": len(annotated),
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "daily",
        "ticker": ticker,
    }


def _portfolio_value(cash, positions, mark_price):
    holdings = sum(qty * mark_price for qty in positions.values())
    return cash + holdings


def _compute_stop(candle):
    atr = candle.get("atr14") or 0
    low = candle.get("low") or candle.get("close") or 0
    ema20 = candle.get("ema20")
    if ema20 is not None and low <= ema20:
        return low - atr
    return low - 1.5 * atr
