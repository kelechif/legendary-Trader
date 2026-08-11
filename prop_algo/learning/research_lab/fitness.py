import numpy as np

def compute_fitness(pnl_series):
    total_return = pnl_series.sum()
    volatility = pnl_series.std()
    sharpe = total_return / (volatility + 1e-9)

    max_dd = 0
    peak = 0
    equity = pnl_series.cumsum()
    for x in equity:
        peak = max(peak, x)
        dd = peak - x
        max_dd = max(max_dd, dd)

    stability = 1.0 / (1.0 + max_dd)

    return {
        "total_return": float(total_return),
        "volatility": float(volatility),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_dd),
        "stability": float(stability),
        "fitness": float(sharpe * stability)
    }
