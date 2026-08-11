"""Multi-asset universe backtest with ranked entries and regime gating."""

import time
from collections import defaultdict

from services.execution_engine.performance import compute_metrics
from services.strategy_engine import choose_signal
from services.strategy_engine.regime import classify_regime, entry_allowed
from services.strategy_engine.signal_scanner import rank_entry_candidates, trend_score
from services.training_engine.backtest import _apply_costs, _compute_stop


def _date_key(candle: dict) -> str:
    return str(candle.get("date") or "")


def _nav(cash, positions, mark_prices):
    return cash + sum(positions.get(t, 0) * mark_prices.get(t, 0) for t in positions)


def run_backtest_universe(
    ticker_candles: dict,
    strategy_name: str,
    params=None,
    initial_equity=100000.0,
    max_positions=10,
    slippage_bps=5,
    commission=1.0,
    regime_cfg=None,
    min_warmup=220,
):
    """Simulate ranked multi-asset portfolio across a shared daily timeline."""
    params = params or {}
    regime_cfg = regime_cfg or {}

    date_indices = {}
    all_dates = set()
    for ticker, candles in ticker_candles.items():
        if len(candles) < min_warmup:
            continue
        mapping = {}
        for i, c in enumerate(candles):
            d = _date_key(c)
            if d:
                mapping[d] = i
                all_dates.add(d)
        if mapping:
            date_indices[ticker] = mapping

    if not all_dates:
        return {"error": "No aligned daily data for universe backtest"}

    sorted_dates = sorted(all_dates)
    cash = initial_equity
    positions = {}
    entry_prices = {}
    stops = {}
    equity_curve = []
    trades = []
    per_ticker_pnl = defaultdict(float)

    for date in sorted_dates:
        day_candidates = []
        mark_prices = {}

        for ticker, mapping in date_indices.items():
            idx = mapping.get(date)
            if idx is None:
                continue

            candles = ticker_candles[ticker]
            current = dict(candles[idx])
            current["ticker"] = ticker
            price = current.get("close")
            if price is None:
                continue
            mark_prices[ticker] = price

            if idx < min_warmup:
                continue

            signal = choose_signal(strategy_name, [], params, candles[: idx + 1])

            if ticker in positions and stops.get(ticker) is not None:
                stop = stops[ticker]
                if current.get("low") is not None and current["low"] <= stop:
                    qty = positions.pop(ticker)
                    entry = entry_prices.pop(ticker)
                    pnl = _apply_costs(entry, stop, qty * entry, slippage_bps, commission)
                    cash += qty * stop - commission
                    per_ticker_pnl[ticker] += pnl
                    trades.append(
                        {
                            "date": date,
                            "ticker": ticker,
                            "action": "STOP",
                            "price": stop,
                            "shares": qty,
                            "pnl": round(pnl, 2),
                        }
                    )
                    stops.pop(ticker, None)
                    continue

            if signal == "SELL" and ticker in positions:
                qty = positions.pop(ticker)
                entry = entry_prices.pop(ticker)
                pnl = _apply_costs(entry, price, qty * entry, slippage_bps, commission)
                cash += qty * price - commission
                per_ticker_pnl[ticker] += pnl
                trades.append(
                    {
                        "date": date,
                        "ticker": ticker,
                        "action": "SELL",
                        "price": price,
                        "shares": qty,
                        "pnl": round(pnl, 2),
                    }
                )
                stops.pop(ticker, None)

            if signal == "BUY" and ticker not in positions:
                regime = classify_regime(current, params)
                if entry_allowed(regime, regime_cfg):
                    day_candidates.append(
                        {
                            "asset": ticker,
                            "signal": "BUY",
                            "score": trend_score(current, params),
                            "regime_label": regime,
                            "close": price,
                            "idx": idx,
                        }
                    )

        ranked = rank_entry_candidates(day_candidates)
        slots = max_positions - len(positions)
        nav = _nav(cash, positions, mark_prices)

        for row in ranked:
            if slots <= 0:
                break
            ticker = row["asset"]
            if ticker in positions:
                continue
            price = row["close"]
            if not price:
                continue

            nav = _nav(cash, positions, mark_prices)
            slot_value = nav / max(max_positions, 1)
            qty = int(slot_value / price) if price > 0 else 0
            cost = qty * price + commission
            if qty <= 0 or cost > cash:
                continue

            cash -= cost
            positions[ticker] = qty
            entry_prices[ticker] = price
            stops[ticker] = _compute_stop(ticker_candles[ticker][row["idx"]])
            mark_prices[ticker] = price
            trades.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "action": "BUY",
                    "price": price,
                    "shares": qty,
                    "score": row["score"],
                    "regime_label": row["regime_label"],
                }
            )
            slots -= 1

        equity_curve.append(_nav(cash, positions, mark_prices))

    if not equity_curve:
        equity_curve = [initial_equity]

    metrics = compute_metrics(equity_curve, trades, periods_per_year=252)
    top_contributors = sorted(per_ticker_pnl.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "strategy": strategy_name,
        "params": params,
        "mode": "universe",
        "tickers": len(ticker_candles),
        "dates": len(sorted_dates),
        "equity_curve": equity_curve,
        "trades": trades,
        "metrics": metrics,
        "top_contributors": [{"ticker": t, "pnl": round(p, 2)} for t, p in top_contributors],
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
