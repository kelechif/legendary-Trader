import threading
import time
import uuid

from services.shared.config import ALERTS_CFG

_lock = threading.Lock()
_alerts = []
_seen_ids = set()


def _enabled():
    return ALERTS_CFG.get("enabled", True)


def emit(level, category, message, asset=None, meta=None):
    if not _enabled():
        return None

    alert = {
        "id": str(uuid.uuid4())[:8],
        "time": time.strftime("%H:%M:%S"),
        "level": level,
        "category": category,
        "message": message,
        "asset": asset,
        "meta": meta or {},
    }

    with _lock:
        _alerts.append(alert)
        if len(_alerts) > 100:
            _alerts.pop(0)

    return alert


def trade_alert(asset, action, price):
    return emit("info", "trade", f"{action} {asset} @ {price:.2f}", asset=asset, meta={"action": action, "price": price})


def signal_alert(asset, signal, strategy):
    return emit("info", "signal", f"{strategy}: {signal} on {asset}", asset=asset, meta={"signal": signal, "strategy": strategy})


def drawdown_alert(asset, drawdown_pct):
    threshold = float(ALERTS_CFG.get("drawdown_threshold_pct", 5.0))
    if drawdown_pct < threshold:
        return None
    key = f"dd_{asset}_{int(drawdown_pct)}"
    with _lock:
        if key in _seen_ids:
            return None
        _seen_ids.add(key)
    return emit("warning", "drawdown", f"{asset} drawdown {drawdown_pct:.1f}%", asset=asset, meta={"drawdown_pct": drawdown_pct})


def get_recent(limit=20):
    with _lock:
        return list(_alerts[-limit:])


def get_config():
    return {
        "enabled": ALERTS_CFG.get("enabled", True),
        "sound": ALERTS_CFG.get("sound", True),
        "popup": ALERTS_CFG.get("popup", True),
        "flash": ALERTS_CFG.get("flash", True),
        "drawdown_threshold_pct": ALERTS_CFG.get("drawdown_threshold_pct", 5.0),
    }
