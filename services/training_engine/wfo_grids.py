"""Walk-forward optimization parameter grids."""

CORE_GRID = {
    "rsi_regime_min": [40, 45, 50],
    "rsi_regime_max": [60, 65, 70],
    "rsi_entry_max": [65, 70, 75],
}

EXPANDED_GRID = {
    "ema_fast": [8, 10, 12],
    "ema_slow": [18, 20, 22],
    "atr_len": [10, 14],
    "rsi_len": [10, 14],
    "rsi_regime_min": [45, 50],
    "rsi_regime_max": [60, 65],
    "rsi_entry_max": [65, 70],
    "rsi_exhaustion": [72, 75],
}

GRIDS = {
    "core": CORE_GRID,
    "expanded": EXPANDED_GRID,
}


def combo_count(grid: dict) -> int:
    n = 1
    for values in grid.values():
        n *= len(values)
    return n
