import threading
import time

from services.execution_engine.moomoo_broker import place_market_order_safe, use_moomoo_broker
from services.market_data import state
from services.market_data.moomoo_feed import get_daily_candles, refresh_all
from services.execution_engine.performance import max_drawdown
from services.risk_governance import alerts
from services.shared.config import (
    ASSETS,
    ENGINE_INTERVAL_SEC,
    EQUITY_HISTORY_LIMIT,
    INITIAL_EQUITY,
    IS_EQUITY_MODE,
    TRADE_HISTORY_LIMIT,
    TRADING_CFG,
    get_strategy_params,
)
from services.shared import log_channels, metrics
from services.strategy_engine import choose_signal
from services.strategy_engine.signal_scanner import rank_entry_candidates, scan_universe

lock = threading.Lock()

current_equity = {a: INITIAL_EQUITY for a in ASSETS}
position = {a: 0 for a in ASSETS}
shares = {a: 0 for a in ASSETS}
cash = INITIAL_EQUITY
last_price = {a: None for a in ASSETS}
trade_history = {a: [] for a in ASSETS}
equity_curve = {a: [] for a in ASSETS}
portfolio_equity_curve = []
_peak_nav = INITIAL_EQUITY
_drawdown_halt_logged = False
current_strategy = "InstitutionalTrend" if IS_EQUITY_MODE else "Momentum"
strategy_params = {}
_last_bar_date = {a: None for a in ASSETS}
_last_scan = {"summary": {}, "entries": [], "scanned": []}


def get_params(strategy=None):
    name = strategy or current_strategy
    with lock:
        merged = dict(get_strategy_params(name))
        merged.update(strategy_params.get(name, {}))
    return merged


def set_strategy(name, strategies):
    global current_strategy
    with lock:
        if name in strategies:
            current_strategy = name
        strategy = current_strategy
    return strategy


def set_params(strategy, params):
    with lock:
        strategy_params[strategy] = dict(params)
    return get_params(strategy)


def portfolio_nav(prices=None):
    prices = prices or {}
    total = cash
    for asset in ASSETS:
        qty = shares.get(asset, 0)
        price = prices.get(asset) or last_price.get(asset)
        if qty and price:
            total += qty * price
    return total


def _max_positions():
    return int(TRADING_CFG.get("max_positions", 10))


def _safe_mode():
    return bool(TRADING_CFG.get("safe_mode", True))


def _trading_enabled():
    return bool(TRADING_CFG.get("enabled", True))


def _max_exposure_pct():
    return float(TRADING_CFG.get("max_exposure_pct", 0.70))


def _drawdown_halt_pct():
    return float(TRADING_CFG.get("drawdown_halt_pct", 0))


def _update_peak_nav(nav):
    global _peak_nav
    if nav > _peak_nav:
        _peak_nav = nav


def _portfolio_drawdown_pct(nav):
    if _peak_nav <= 0:
        return 0.0
    return ((_peak_nav - nav) / _peak_nav) * 100.0


def drawdown_halt_active(nav=None):
    halt_pct = _drawdown_halt_pct()
    if halt_pct <= 0:
        return False
    if nav is None:
        nav = portfolio_nav()
    return _portfolio_drawdown_pct(nav) >= halt_pct


def get_trading_guard_status():
    """Return drawdown halt and buy eligibility for API consumers."""
    with lock:
        nav = portfolio_nav(
            {a: state.latest_price.get(a) or last_price.get(a) for a in ASSETS}
        )
        nav = nav if nav > 0 else cash
        halt = drawdown_halt_active(nav)
        status = {
            "nav": nav,
            "peak_nav": _peak_nav,
            "drawdown_pct": round(_portfolio_drawdown_pct(nav), 4),
            "drawdown_halt_pct": _drawdown_halt_pct(),
            "drawdown_halt_active": halt,
            "can_buy": not halt,
        }
        if use_moomoo_broker():
            from services.execution_engine.moomoo_broker import can_place_buy

            ok, reason, snap = can_place_buy("", 0, 0)
            status["power"] = snap.get("power", 0)
            status["total_assets"] = snap.get("total_assets", 0)
            status["min_power_threshold"] = snap.get("min_power_threshold")
            status["can_buy"] = (not halt) and ok
            if not ok:
                status["buy_block_reason"] = reason
        else:
            status["power"] = cash
            status["total_assets"] = nav
        return status


def _log_drawdown_halt(nav):
    global _drawdown_halt_logged
    if not drawdown_halt_active(nav):
        _drawdown_halt_logged = False
        return
    if _drawdown_halt_logged:
        return
    _drawdown_halt_logged = True
    log_channels.log_event(
        "execution",
        "drawdown_halt_active",
        nav=nav,
        peak_nav=_peak_nav,
        drawdown_pct=round(_portfolio_drawdown_pct(nav), 4),
        drawdown_halt_pct=_drawdown_halt_pct(),
    )


def _exposure_ok(additional_cost, nav):
    if nav <= 0:
        return False
    invested = nav - cash
    return (invested + additional_cost) / nav <= _max_exposure_pct()


def _equal_weight_shares(price, open_count, nav, slots_available):
    if price <= 0 or slots_available <= 0:
        return 0
    target_value = nav / slots_available
    return int(target_value / price)


def _execute_buy(asset, qty, price, bar_date):
    global cash
    commission = float(TRADING_CFG.get("commission", 1.0))
    cost = qty * price + commission

    if drawdown_halt_active():
        log_channels.log_event(
            "execution",
            "order_skipped",
            ticker=asset,
            reason="drawdown_halt",
            nav=portfolio_nav(),
            peak_nav=_peak_nav,
        )
        return

    if _safe_mode() or not _trading_enabled():
        log_channels.log_event(
            "execution", "buy_simulated", ticker=asset, price=price, shares=qty, safe_mode=True
        )
    elif use_moomoo_broker():
        result = place_market_order_safe(asset, qty, "BUY", price=price)
        if result.get("status") == "skipped":
            return
        cash -= cost
        shares[asset] = qty
        position[asset] = 1
    else:
        cash -= cost
        shares[asset] = qty
        position[asset] = 1

    trade_history[asset].append(
        {"time": bar_date or time.strftime("%Y-%m-%d"), "action": "BUY", "price": price, "shares": qty}
    )
    alerts.trade_alert(asset, "BUY", price)
    metrics.increment("trades_executed")


def _execute_sell(asset, qty, price, bar_date):
    global cash
    commission = float(TRADING_CFG.get("commission", 1.0))
    proceeds = qty * price

    if _safe_mode() or not _trading_enabled():
        log_channels.log_event(
            "execution", "sell_simulated", ticker=asset, price=price, shares=qty, safe_mode=True
        )
    elif use_moomoo_broker():
        place_market_order_safe(asset, qty, "SELL", price=price)
        cash += proceeds - commission
        shares[asset] = 0
        position[asset] = 0
    else:
        cash += proceeds - commission
        shares[asset] = 0
        position[asset] = 0

    trade_history[asset].append(
        {"time": bar_date or time.strftime("%Y-%m-%d"), "action": "SELL", "price": price, "shares": qty}
    )
    alerts.trade_alert(asset, "SELL", price)
    metrics.increment("trades_executed")


def _run_equity_batch(params, strategy):
    """Scan universe, exit first, then rank and fill entry slots."""
    global _last_scan

    scanned = scan_universe(strategy, params)
    from services.strategy_engine.signal_scanner import summarize_scan

    summary = summarize_scan(scanned)
    entries = rank_entry_candidates(scanned)

    with lock:
        nav = portfolio_nav(
            {a: state.latest_price.get(a) or last_price.get(a) for a in ASSETS}
        )
        nav = nav if nav > 0 else cash

        # Phase 1: exits for held positions
        for row in scanned:
            asset = row["asset"]
            candles = get_daily_candles(asset)
            if not candles:
                continue
            bar_date = candles[-1].get("date")
            if _last_bar_date.get(asset) == bar_date:
                continue

            price = row.get("close")
            if price is None:
                continue

            prev_qty = shares.get(asset, 0)
            if row["signal"] == "SELL" and prev_qty > 0:
                _execute_sell(asset, prev_qty, price, bar_date)

            last_price[asset] = price
            _last_bar_date[asset] = bar_date

        open_positions = sum(1 for a in ASSETS if shares.get(a, 0) > 0)
        slots = _max_positions() - open_positions
        _update_peak_nav(nav)
        _log_drawdown_halt(nav)
        entries_blocked = drawdown_halt_active(nav)

        # Phase 2: ranked entries
        for row in entries:
            if slots <= 0 or entries_blocked:
                break
            asset = row["asset"]
            if shares.get(asset, 0) > 0:
                continue

            candles = get_daily_candles(asset)
            if not candles:
                continue
            bar_date = candles[-1].get("date")
            price = row.get("close")
            if price is None:
                continue

            qty = _equal_weight_shares(price, open_positions, nav, slots)
            cost = qty * price + float(TRADING_CFG.get("commission", 1.0))
            if qty <= 0 or cost > cash or not _exposure_ok(cost, nav):
                continue

            _execute_buy(asset, qty, price, bar_date)
            last_price[asset] = price
            _last_bar_date[asset] = bar_date
            open_positions += 1
            slots -= 1
            nav = portfolio_nav(dict(last_price))

        _last_scan = {"summary": summary, "entries": entries[:20], "scanned": scanned}

        portfolio_equity_curve.append(portfolio_nav(dict(last_price)))
        if len(portfolio_equity_curve) > EQUITY_HISTORY_LIMIT:
            portfolio_equity_curve.pop(0)
        _update_peak_nav(portfolio_equity_curve[-1] if portfolio_equity_curve else nav)
        alerts.drawdown_alert("PORTFOLIO", max_drawdown(portfolio_equity_curve))

    log_channels.log_event(
        "signal",
        "universe_scan",
        **summary,
        top_entries=[e["asset"] for e in entries[:5]],
    )


def _process_tick_asset(asset, params, strategy):
    with state.lock:
        price = state.latest_price[asset]
        prices = list(state.price_history[asset])

    if price is None:
        return

    signal = choose_signal(strategy, prices, params)

    with lock:
        lp = last_price[asset]
        if lp is not None:
            if position[asset] == 1:
                current_equity[asset] += price - lp
            elif position[asset] == -1:
                current_equity[asset] += lp - price

        prev_pos = position[asset]

        if signal == "BUY" and position[asset] <= 0:
            position[asset] = 1
            trade_history[asset].append(
                {"time": time.strftime("%H:%M:%S"), "action": "BUY", "price": price}
            )
            alerts.trade_alert(asset, "BUY", price)
            metrics.increment("trades_executed")
        elif signal == "SELL" and position[asset] >= 0:
            position[asset] = -1
            trade_history[asset].append(
                {"time": time.strftime("%H:%M:%S"), "action": "SELL", "price": price}
            )
            alerts.trade_alert(asset, "SELL", price)
            metrics.increment("trades_executed")

        if signal in ("BUY", "SELL") and prev_pos != position[asset]:
            alerts.signal_alert(asset, signal, strategy)

        if len(trade_history[asset]) > TRADE_HISTORY_LIMIT:
            trade_history[asset].pop(0)

        equity_curve[asset].append(current_equity[asset])
        if len(equity_curve[asset]) > EQUITY_HISTORY_LIMIT:
            equity_curve[asset].pop(0)

        last_price[asset] = price
        dd = max_drawdown(equity_curve[asset])
        alerts.drawdown_alert(asset, dd)


def engine_loop():
    while True:
        with lock:
            strategy = current_strategy
            params = dict(get_strategy_params(strategy))
            params.update(strategy_params.get(strategy, {}))

        if IS_EQUITY_MODE:
            _run_equity_batch(params, strategy)
        else:
            for asset in ASSETS:
                _process_tick_asset(asset, params, strategy)

        metrics.increment("engine_ticks")
        time.sleep(ENGINE_INTERVAL_SEC)


def run_daily_cycle(logger=None):
    """Refresh Moomoo data and run one ranked equity cycle."""
    params = get_params()
    refresh_all(params)
    with lock:
        strategy = current_strategy
    _run_equity_batch(params, strategy)
    if logger:
        logger.info("Daily cycle complete for %s assets", len(ASSETS))
    log_channels.log_event("system", "daily_cycle_complete", assets=len(ASSETS))


def get_last_scan():
    with lock:
        return dict(_last_scan)


def start():
    threading.Thread(target=engine_loop, daemon=True, name="paper-trader").start()
