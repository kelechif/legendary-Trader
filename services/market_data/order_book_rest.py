import json
import logging
import threading
import time
import urllib.request

from services.market_data import state
from services.market_data.order_book import apply_snapshot
from services.shared.config import ASSETS
from services.shared import metrics

_log = logging.getLogger("quant-platform")
_thread = None
INTERVAL_SEC = 5


def _fetch_book(asset):
    url = f"https://api.exchange.coinbase.com/products/{asset}/book?level=2"
    req = urllib.request.Request(url, headers={"User-Agent": "QuantPlatform/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    bids = data.get("bids", [])
    asks = data.get("asks", [])
    return bids, asks


def poll_loop():
    while True:
        for asset in ASSETS:
            try:
                bids, asks = _fetch_book(asset)
                with state.lock:
                    apply_snapshot(state.order_books[asset], bids, asks)
                metrics.increment("orderbook_snapshots")
            except Exception as exc:
                _log.warning("Order book fetch failed for %s: %s", asset, exc)
        time.sleep(INTERVAL_SEC)


def start():
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=poll_loop, daemon=True, name="orderbook-rest")
    _thread.start()
