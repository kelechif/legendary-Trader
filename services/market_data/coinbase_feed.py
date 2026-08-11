import json
import threading
import time
from datetime import datetime

from websocket import WebSocketApp

from services.market_data import state
from services.market_data.candles import append_candle, bucket_timestamp
from services.shared.config import (
    ASSETS,
    CANDLE_TIMEFRAMES,
    PRICE_HISTORY_LIMIT,
    WS_RECONNECT_DELAY_SEC,
)
from services.shared import metrics

_ws_thread = None
_log = None


def _log_info(msg):
    if _log:
        _log.info(msg)


def _update_candles(asset, price, ts):
    with state.lock:
        for tf in CANDLE_TIMEFRAMES:
            bucket = bucket_timestamp(ts, tf)
            if state.candle_bucket[asset][tf] is None:
                state.candle_bucket[asset][tf] = bucket

            if bucket != state.candle_bucket[asset][tf]:
                append_candle(
                    state.candle_history[asset][tf],
                    state.candle_buffers[asset][tf],
                )
                state.candle_buffers[asset][tf] = [price]
                state.candle_bucket[asset][tf] = bucket
            else:
                state.candle_buffers[asset][tf].append(price)


def _handle_ticker(msg):
    asset = msg.get("product_id")
    if asset not in ASSETS:
        return

    try:
        price = float(msg.get("price"))
    except (TypeError, ValueError):
        return

    ts_str = msg.get("time")
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return

    with state.lock:
        state.latest_price[asset] = price
        state.price_history[asset].append(price)
        if len(state.price_history[asset]) > PRICE_HISTORY_LIMIT:
            state.price_history[asset].pop(0)

    _update_candles(asset, price, ts)
    metrics.increment("ticks_received")
    metrics.set_gauge(f"price_{asset}", price)


def on_message(_ws, message):
    try:
        msg = json.loads(message)
    except json.JSONDecodeError:
        return

    msg_type = msg.get("type")
    if msg_type == "ticker":
        _handle_ticker(msg)
    elif msg_type == "error":
        if _log:
            _log.error("WebSocket error message: %s", msg.get("message"))


def on_open(ws):
    sub = {
        "type": "subscribe",
        "channels": [{"name": "ticker", "product_ids": ASSETS}],
    }
    ws.send(json.dumps(sub))
    _log_info(f"Subscribed to ticker for {ASSETS}")


def on_error(_ws, err):
    if _log:
        _log.error("WebSocket error: %s", err)


def ws_loop():
    while True:
        ws = WebSocketApp(
            "wss://ws-feed.exchange.coinbase.com",
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
        )
        ws.run_forever()
        _log_info("WebSocket closed — reconnecting...")
        time.sleep(WS_RECONNECT_DELAY_SEC)


def start(logger=None):
    global _ws_thread, _log
    _log = logger
    if _ws_thread and _ws_thread.is_alive():
        return
    _ws_thread = threading.Thread(target=ws_loop, daemon=True, name="coinbase-ws")
    _ws_thread.start()
