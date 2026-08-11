"""Moomoo OpenSecTradeContext adapter (SIMULATE by default)."""

from services.shared.config import MOOMOO_HOST, MOOMOO_PORT, TRADING_CFG
from services.shared import log_channels

_acc_cache = None


def clear_account_cache() -> None:
    """Reset cached simulate account id (e.g. after config reload)."""
    global _acc_cache
    _acc_cache = None


def _simulate_acc_type_pref() -> str | None:
    pref = TRADING_CFG.get("simulate_acc_type")
    return str(pref).upper() if pref else None


def _min_power_threshold(total_assets: float) -> float:
    if TRADING_CFG.get("min_buying_power") is not None:
        return float(TRADING_CFG["min_buying_power"])
    pct = TRADING_CFG.get("min_power_pct")
    if pct is not None and total_assets > 0:
        return total_assets * float(pct)
    return float(TRADING_CFG.get("min_buying_power", 1000))


def _trd_env():
    from moomoo import TrdEnv

    env_name = str(TRADING_CFG.get("env", "SIMULATE")).upper()
    if env_name == "REAL":
        return TrdEnv.REAL
    return TrdEnv.SIMULATE


def _trd_market():
    from moomoo import TrdMarket

    market = str(TRADING_CFG.get("trd_market", "US")).upper()
    return getattr(TrdMarket, market, TrdMarket.US)


def _trade_context():
    from moomoo import OpenSecTradeContext

    return OpenSecTradeContext(
        filter_trdmarket=_trd_market(),
        host=MOOMOO_HOST,
        port=MOOMOO_PORT,
    )


def _pick_simulate_account(sim) -> int | None:
    """Pick SIMULATE acc_id, preferring configured acc_type (CASH over MARGIN fallback)."""
    from moomoo import TrdAccType

    pref = _simulate_acc_type_pref()
    if pref and "acc_type" in sim.columns:
        type_val = getattr(TrdAccType, pref, None)
        if type_val is not None:
            typed = sim[sim["acc_type"] == type_val]
            if not typed.empty:
                return int(typed.iloc[0]["acc_id"])
        if pref == "CASH":
            margin = sim[sim["acc_type"] == TrdAccType.MARGIN]
            if not margin.empty:
                return int(margin.iloc[0]["acc_id"])
    return int(sim.iloc[0]["acc_id"]) if not sim.empty else None


def get_simulate_account_id() -> int | None:
    """Resolve US SIMULATE account id (cached)."""
    global _acc_cache
    if _acc_cache is not None:
        return _acc_cache

    configured = TRADING_CFG.get("simulate_acc_id")
    if configured:
        _acc_cache = int(configured)
        return _acc_cache

    from moomoo import RET_OK, TrdEnv

    ctx = _trade_context()
    try:
        ret, accs = ctx.get_acc_list()
        if ret != RET_OK or accs is None or accs.empty:
            return None
        sim = accs[accs["trd_env"] == TrdEnv.SIMULATE]
        if sim.empty:
            return None
        _acc_cache = _pick_simulate_account(sim)
        return _acc_cache
    finally:
        ctx.close()


def get_account_snapshot() -> dict:
    """Return simulate account buying power and positions summary."""
    from moomoo import RET_OK

    acc_id = get_simulate_account_id()
    if not acc_id:
        return {"error": "No SIMULATE account found"}

    env = _trd_env()
    ctx = _trade_context()
    try:
        ret, funds = ctx.accinfo_query(trd_env=env, acc_id=acc_id)
        ret2, positions = ctx.position_list_query(trd_env=env, acc_id=acc_id)
        if ret != RET_OK:
            return {"error": str(funds), "acc_id": acc_id}
        power = float(funds["power"].iloc[0]) if funds is not None and len(funds) else 0.0
        total_assets = float(funds["total_assets"].iloc[0]) if funds is not None and len(funds) else 0.0
        pos_count = len(positions) if ret2 == RET_OK and positions is not None else 0
        threshold = _min_power_threshold(total_assets)
        return {
            "acc_id": acc_id,
            "env": str(env),
            "power": power,
            "total_assets": total_assets,
            "positions": pos_count,
            "min_power_threshold": threshold,
            "can_buy": power >= threshold,
        }
    finally:
        ctx.close()


def can_place_buy(code: str, qty: int, price: float) -> tuple[bool, str, dict]:
    """Pre-trade margin guard using accinfo_query buying power."""
    snap = get_account_snapshot()
    if snap.get("error"):
        return False, "account_error", snap

    power = float(snap.get("power", 0))
    total_assets = float(snap.get("total_assets", 0))
    threshold = _min_power_threshold(total_assets)
    snap["min_power_threshold"] = threshold

    if power < threshold:
        snap["reason"] = "min_buying_power"
        return False, "min_buying_power", snap

    if price > 0 and qty > 0 and power < qty * price:
        snap["reason"] = "insufficient_buying_power"
        return False, "insufficient_buying_power", snap

    return True, "", snap


def max_buy_qty(code: str, price: float) -> int:
    """Query max cash-buy quantity from OpenD."""
    from moomoo import OrderType, RET_OK

    acc_id = get_simulate_account_id()
    if not acc_id or price <= 0:
        return 0

    ctx = _trade_context()
    try:
        ret, data = ctx.acctradinginfo_query(
            order_type=OrderType.NORMAL,
            code=code,
            price=price,
            trd_env=_trd_env(),
            acc_id=acc_id,
        )
        if ret != RET_OK or data is None or data.empty:
            return 0
        return int(data["max_cash_buy"].iloc[0])
    finally:
        ctx.close()


def place_market_order(code: str, qty: int, side: str) -> dict:
    """
    Place a market order via Moomoo OpenD (US SIMULATE by default).
    side: BUY | SELL
    """
    from moomoo import OrderType, RET_OK, TrdSide

    if qty <= 0:
        return {"status": "skipped", "reason": "zero_qty"}

    acc_id = get_simulate_account_id()
    if not acc_id:
        raise RuntimeError("No Moomoo SIMULATE account available for US market")

    trd_side = TrdSide.BUY if side.upper() == "BUY" else TrdSide.SELL
    env = _trd_env()

    ctx = _trade_context()
    try:
        ret, data = ctx.place_order(
            price=0,
            qty=qty,
            code=code,
            trd_side=trd_side,
            order_type=OrderType.MARKET,
            trd_env=env,
            acc_id=acc_id,
        )
    finally:
        ctx.close()

    if ret != RET_OK:
        msg = str(data) if data is not None else f"ret={ret}"
        raise RuntimeError(f"Moomoo order failed for {code} {side} x{qty}: {msg}")

    order_id = None
    if data is not None and hasattr(data, "iloc") and len(data):
        order_id = data.iloc[0].get("order_id")

    result = {
        "status": "ok",
        "code": code,
        "side": side,
        "qty": qty,
        "order_id": order_id,
        "env": str(env),
        "acc_id": acc_id,
    }
    log_channels.log_event("execution", "moomoo_order", **result)
    return result


def place_market_order_safe(code: str, qty: int, side: str, price: float | None = None) -> dict:
    """Cap buy qty to OpenD max and skip if margin guard fails."""
    if side.upper() == "BUY":
        ok, reason, snap = can_place_buy(code, qty, price or 0)
        if not ok:
            log_channels.log_event(
                "execution",
                "order_skipped",
                ticker=code,
                reason=reason,
                power=snap.get("power", 0),
                total_assets=snap.get("total_assets", 0),
                min_power_threshold=snap.get("min_power_threshold"),
            )
            return {"status": "skipped", "reason": reason, "code": code}

        if price and price > 0:
            allowed = max_buy_qty(code, price)
            if allowed <= 0:
                log_channels.log_event(
                    "execution",
                    "order_skipped",
                    ticker=code,
                    reason="insufficient_buying_power",
                    power=snap.get("power", 0),
                )
                return {"status": "skipped", "reason": "insufficient_buying_power", "code": code}
            qty = min(qty, allowed)
    return place_market_order(code, qty, side)


def use_moomoo_broker() -> bool:
    return str(TRADING_CFG.get("broker", "internal")).lower() == "moomoo"
