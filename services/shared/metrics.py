import threading
import time
from collections import defaultdict

from services.shared.config import METRICS_CFG

_lock = threading.Lock()
_counters = defaultdict(int)
_gauges = {}
_timestamps = {}


def enabled():
    return METRICS_CFG.get("enabled", True)


def increment(name, value=1):
    if not enabled():
        return
    with _lock:
        _counters[name] += value
        _timestamps[name] = time.time()


def set_gauge(name, value):
    if not enabled():
        return
    with _lock:
        _gauges[name] = value
        _timestamps[name] = time.time()


def snapshot():
    with _lock:
        return {
            "counters": dict(_counters),
            "gauges": dict(_gauges),
            "updated_at": dict(_timestamps),
        }


def reset():
    with _lock:
        _counters.clear()
        _gauges.clear()
        _timestamps.clear()
