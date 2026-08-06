from services.shared.config import ASSETS, INITIAL_EQUITY, IS_EQUITY_MODE, TRADING_CFG


def build_snapshot(latest_prices, positions, equities, trades, shares=None, cash=0.0, nav=0.0):
    if IS_EQUITY_MODE:
        return _equity_snapshot(latest_prices, shares or {}, cash, nav, trades)

    total_equity = sum(equities.get(a, INITIAL_EQUITY) for a in ASSETS)
    holdings = []

    for asset in ASSETS:
        pos = positions.get(asset, 0)
        price = latest_prices.get(asset)
        equity = equities.get(asset, INITIAL_EQUITY)
        exposure = 0.0
        if price and pos != 0:
            exposure = price if pos == 1 else -price

        holdings.append(
            {
                "asset": asset,
                "position": pos,
                "position_label": {1: "LONG", -1: "SHORT", 0: "FLAT"}.get(pos, "FLAT"),
                "price": price,
                "equity": round(equity, 2),
                "allocation_pct": round(equity / total_equity * 100, 1) if total_equity else 0,
                "exposure": exposure,
                "trade_count": len(trades.get(asset, [])),
            }
        )

    return {
        "total_equity": round(total_equity, 2),
        "initial_equity": INITIAL_EQUITY * len(ASSETS),
        "pnl": round(total_equity - INITIAL_EQUITY * len(ASSETS), 2),
        "holdings": holdings,
        "mode": "tick",
    }


def _equity_snapshot(latest_prices, shares, cash, nav, trades):
    total_equity = nav if nav > 0 else cash
    holdings = []
    invested = 0.0

    for asset in ASSETS:
        qty = shares.get(asset, 0)
        price = latest_prices.get(asset)
        market_value = (qty * price) if price and qty else 0.0
        invested += market_value
        pos_label = "LONG" if qty > 0 else "FLAT"

        holdings.append(
            {
                "asset": asset,
                "position": 1 if qty > 0 else 0,
                "position_label": pos_label,
                "shares": qty,
                "price": price,
                "market_value": round(market_value, 2),
                "equity": round(market_value, 2),
                "allocation_pct": round(market_value / total_equity * 100, 1) if total_equity else 0,
                "exposure": market_value,
                "trade_count": len(trades.get(asset, [])),
            }
        )

    max_exp = float(TRADING_CFG.get("max_exposure_pct", 0.70))
    exposure_pct = invested / total_equity if total_equity else 0

    return {
        "total_equity": round(total_equity, 2),
        "cash": round(cash, 2),
        "invested": round(invested, 2),
        "exposure_pct": round(exposure_pct * 100, 1),
        "max_exposure_pct": round(max_exp * 100, 1),
        "initial_equity": INITIAL_EQUITY,
        "pnl": round(total_equity - INITIAL_EQUITY, 2),
        "holdings": holdings,
        "mode": "equity",
    }
