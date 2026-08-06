import math


def _returns(series):
    if len(series) < 2:
        return []
    return [(series[i] - series[i - 1]) / series[i - 1] if series[i - 1] else 0 for i in range(1, len(series))]


def sharpe_ratio(equity_curve, periods_per_year=252 * 24 * 30):
    """Sharpe on equity step returns (approx)."""
    rets = _returns(equity_curve)
    if len(rets) < 2:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    std = math.sqrt(var) if var > 0 else 0
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(periods_per_year)


def max_drawdown(equity_curve):
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak else 0
        max_dd = max(max_dd, dd)
    return max_dd * 100


def win_rate(trades):
    """Win rate from paired round-trip trades."""
    if len(trades) < 2:
        return 0.0
    wins = 0
    total = 0
    i = 0
    while i < len(trades) - 1:
        entry = trades[i]
        exit_ = trades[i + 1]
        if entry["action"] == "BUY" and exit_["action"] == "SELL":
            pnl = exit_["price"] - entry["price"]
        elif entry["action"] == "SELL" and exit_["action"] == "BUY":
            pnl = entry["price"] - exit_["price"]
        else:
            i += 1
            continue
        total += 1
        if pnl > 0:
            wins += 1
        i += 2
    return (wins / total * 100) if total else 0.0


def compute_metrics(equity_curve, trades, periods_per_year=252 * 24 * 30):
    return {
        "sharpe": round(sharpe_ratio(equity_curve, periods_per_year), 3),
        "max_drawdown_pct": round(max_drawdown(equity_curve), 2),
        "win_rate_pct": round(win_rate(trades), 1),
        "total_trades": len(trades),
        "current_equity": equity_curve[-1] if equity_curve else 0,
    }


def aggregate_metrics(equity_by_asset, trades_by_asset):
    per_asset = {}
    for asset in equity_by_asset:
        per_asset[asset] = compute_metrics(equity_by_asset[asset], trades_by_asset.get(asset, []))

    combined_equity = []
    if equity_by_asset:
        max_len = max(len(v) for v in equity_by_asset.values())
        for i in range(max_len):
            combined_equity.append(sum(v[i] if i < len(v) else v[-1] for v in equity_by_asset.values()))

    all_trades = []
    for trades in trades_by_asset.values():
        all_trades.extend(trades)

    portfolio = compute_metrics(combined_equity, all_trades)
    portfolio["combined_equity"] = combined_equity[-1] if combined_equity else 0
    return {"portfolio": portfolio, "assets": per_asset}
