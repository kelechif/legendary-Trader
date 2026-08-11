"""Moomoo OpenD US options execution (single-leg + combo spreads)."""

from __future__ import annotations

from services.execution_engine import moomoo_broker
from services.shared.config import OPTIONS_CFG, TRADING_CFG
from services.shared import log_channels


def _mm_cfg() -> dict:
    return OPTIONS_CFG.get("moomoo", {})


def _safe_mode() -> bool:
    if "safe_mode" in _mm_cfg():
        return bool(_mm_cfg()["safe_mode"])
    return bool(TRADING_CFG.get("safe_mode", True))


def use_moomoo_options() -> bool:
    broker = str(OPTIONS_CFG.get("execution", {}).get("broker", "")).lower()
    if broker == "moomoo":
        return True
    return str(TRADING_CFG.get("broker", "")).lower() == "moomoo" and OPTIONS_CFG.get("moomoo")


def _acc_id() -> int | None:
    return moomoo_broker.get_simulate_account_id()


def place_option_order(
    code: str,
    qty: int,
    side: str,
    *,
    price: float = 0.0,
    order_type: str = "MARKET",
) -> dict:
    """Place single US option order (qty in contracts)."""
    from moomoo import OrderType, RET_OK, TrdSide

    if qty <= 0:
        return {"status": "skipped", "reason": "zero_qty", "code": code}

    if _safe_mode():
        result = {
            "status": "simulated",
            "code": code,
            "side": side,
            "qty": qty,
            "price": price,
            "order_type": order_type,
        }
        log_channels.log_event("execution", "moomoo_option_sim", **result)
        return result

    acc_id = _acc_id()
    if not acc_id:
        raise RuntimeError("No Moomoo SIMULATE account for US options")

    trd_side = TrdSide.BUY if side.upper() == "BUY" else TrdSide.SELL
    otype = OrderType.MARKET if order_type.upper() == "MARKET" else OrderType.NORMAL
    env = moomoo_broker._trd_env()

    ctx = moomoo_broker._trade_context()
    try:
        ret, data = ctx.place_order(
            price=price,
            qty=qty,
            code=code,
            trd_side=trd_side,
            order_type=otype,
            trd_env=env,
            acc_id=acc_id,
        )
    finally:
        ctx.close()

    if ret != RET_OK:
        msg = str(data) if data is not None else f"ret={ret}"
        raise RuntimeError(f"Moomoo option order failed {code} {side} x{qty}: {msg}")

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
    log_channels.log_event("execution", "moomoo_option_order", **result)
    return result


def place_credit_vertical_combo(
    short_code: str,
    long_code: str,
    *,
    qty: int = 1,
    price: float | None = None,
    order_type: str = "NORMAL",
) -> dict:
    """
    Credit vertical via combo order: sell short leg, buy long leg.
    price: net credit limit (required for NORMAL); use strategy analysis bid/ask in production.
    """
    from moomoo import ComboLeg, OrderType, RET_OK, TrdSide

    if qty <= 0:
        return {"status": "skipped", "reason": "zero_qty"}

    def _leg(code: str, side) -> ComboLeg:
        leg = ComboLeg()
        leg.code = code
        leg.trd_side = side
        leg.qty_ratio = 1.0
        return leg

    legs = [_leg(short_code, TrdSide.SELL), _leg(long_code, TrdSide.BUY)]

    if _safe_mode():
        result = {
            "status": "simulated",
            "structure": "credit_vertical",
            "qty": qty,
            "legs": [{"code": short_code, "side": "SELL"}, {"code": long_code, "side": "BUY"}],
            "price": price,
        }
        log_channels.log_event("execution", "moomoo_combo_sim", **result)
        return result

    acc_id = _acc_id()
    if not acc_id:
        raise RuntimeError("No Moomoo SIMULATE account for US options")

    otype = OrderType.MARKET if order_type.upper() == "MARKET" else OrderType.NORMAL
    limit_price = float(price or 0)
    if otype != OrderType.MARKET and limit_price <= 0:
        raise ValueError("Credit vertical limit order requires positive net credit price")

    env = moomoo_broker._trd_env()
    ctx = moomoo_broker._trade_context()
    try:
        ret, data = ctx.place_combo_order(
            combo_leg_list=legs,
            price=limit_price,
            qty=qty,
            order_type=otype,
            trd_env=env,
            acc_id=acc_id,
        )
    finally:
        ctx.close()

    if ret != RET_OK:
        msg = str(data) if data is not None else f"ret={ret}"
        raise RuntimeError(f"Moomoo combo order failed: {msg}")

    order_id = None
    if data is not None and hasattr(data, "iloc") and len(data):
        order_id = data.iloc[0].get("order_id")

    result = {
        "status": "ok",
        "structure": "credit_vertical",
        "qty": qty,
        "legs": [{"code": short_code, "side": "SELL"}, {"code": long_code, "side": "BUY"}],
        "order_id": order_id,
        "price": limit_price,
        "env": str(env),
        "acc_id": acc_id,
    }
    log_channels.log_event("execution", "moomoo_combo_order", **result)
    return result


def close_credit_vertical_combo(
    short_code: str,
    long_code: str,
    *,
    qty: int = 1,
    price: float | None = None,
    order_type: str = "MARKET",
) -> dict:
    """Close credit vertical: buy short leg, sell long leg (debit)."""
    from moomoo import ComboLeg, OrderType, RET_OK, TrdSide

    if qty <= 0:
        return {"status": "skipped", "reason": "zero_qty"}

    def _leg(code: str, side) -> ComboLeg:
        leg = ComboLeg()
        leg.code = code
        leg.trd_side = side
        leg.qty_ratio = 1.0
        return leg

    legs = [_leg(short_code, TrdSide.BUY), _leg(long_code, TrdSide.SELL)]

    if _safe_mode():
        result = {
            "status": "simulated",
            "structure": "close_credit_vertical",
            "qty": qty,
            "legs": [{"code": short_code, "side": "BUY"}, {"code": long_code, "side": "SELL"}],
            "price": price,
        }
        log_channels.log_event("execution", "moomoo_close_combo_sim", **result)
        return result

    acc_id = _acc_id()
    if not acc_id:
        raise RuntimeError("No Moomoo SIMULATE account for US options")

    otype = OrderType.MARKET if order_type.upper() == "MARKET" else OrderType.NORMAL
    limit_price = float(price or 0)

    env = moomoo_broker._trd_env()
    ctx = moomoo_broker._trade_context()
    try:
        ret, data = ctx.place_combo_order(
            combo_leg_list=legs,
            price=limit_price,
            qty=qty,
            order_type=otype,
            trd_env=env,
            acc_id=acc_id,
        )
    finally:
        ctx.close()

    if ret != RET_OK:
        msg = str(data) if data is not None else f"ret={ret}"
        raise RuntimeError(f"Moomoo close combo failed: {msg}")

    order_id = None
    if data is not None and hasattr(data, "iloc") and len(data):
        order_id = data.iloc[0].get("order_id")

    result = {
        "status": "ok",
        "structure": "close_credit_vertical",
        "qty": qty,
        "order_id": order_id,
        "price": limit_price,
    }
    log_channels.log_event("execution", "moomoo_close_combo_order", **result)
    return result


def get_option_positions() -> list[dict]:
    """List open option positions."""
    from moomoo import RET_OK

    acc_id = _acc_id()
    if not acc_id:
        return []

    env = moomoo_broker._trd_env()
    ctx = moomoo_broker._trade_context()
    try:
        ret, data = ctx.position_list_query(trd_env=env, acc_id=acc_id)
        if ret != RET_OK or data is None or data.empty:
            return []
        rows = []
        for _, row in data.iterrows():
            code = str(row.get("code", ""))
            if "option" in code.lower() or len(code) > 12:
                rows.append(row.to_dict())
        return rows
    finally:
        ctx.close()
