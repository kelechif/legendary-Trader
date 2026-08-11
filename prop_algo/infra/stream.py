import json
import os

import pandas as pd
import redis


def _encode(obj):
    if isinstance(obj, pd.DataFrame):
        return {"__df__": True, "data": obj.to_dict(orient="list")}
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, tuple):
                key = json.dumps({"__tuple__": list(k)})
            else:
                key = k
            out[key] = _encode(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [_encode(x) for x in obj]
    return obj


def _decode(obj):
    if isinstance(obj, dict):
        if obj.get("__df__") is True:
            return pd.DataFrame(obj["data"])
        out = {}
        for k, v in obj.items():
            key = k
            if isinstance(k, str) and k.startswith("{"):
                try:
                    meta = json.loads(k)
                    if isinstance(meta, dict) and "__tuple__" in meta:
                        key = tuple(meta["__tuple__"])
                except Exception:
                    key = k
            out[key] = _decode(v)
        return out
    if isinstance(obj, list):
        return [_decode(x) for x in obj]
    return obj


def _stream_maxlen(stream: str) -> int | None:
    """Approximate XADD MAXLEN (~). Env STREAM_MAXLEN (default 10000).

    Optional per-stream override: STREAM_MAXLEN_<STREAM> with non-alnum → `_`
    (e.g. market_data_stream → STREAM_MAXLEN_MARKET_DATA_STREAM).
    Set to 0 (or negative) to disable trimming.
    """
    key = "STREAM_MAXLEN_" + "".join(
        c if c.isalnum() else "_" for c in stream
    ).upper()
    raw = os.getenv(key)
    if raw is None or raw == "":
        raw = os.getenv("STREAM_MAXLEN", "10000")
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 10000
    return n if n > 0 else None


class Stream:
    def __init__(self, host=None, port=None):
        host = host if host is not None else os.getenv("REDIS_HOST", "redis")
        port = int(port if port is not None else os.getenv("REDIS_PORT", "6379"))
        self.r = redis.Redis(host=host, port=port)

    def publish(self, stream, data, maxlen=None):
        if maxlen is None:
            maxlen = _stream_maxlen(stream)
        fields = {"data": json.dumps(_encode(data))}
        if maxlen is not None:
            # redis-py approximate=True → Redis MAXLEN ~
            self.r.xadd(stream, fields, maxlen=maxlen, approximate=True)
        else:
            self.r.xadd(stream, fields)

    def consume(self, stream, group, consumer, block=None, count=1):
        # Blocking XREADGROUP (ms). Avoid spin-polling empty streams.
        if block is None:
            block = int(os.getenv("STREAM_BLOCK_MS", "1000"))
        try:
            self.r.xgroup_create(stream, group, mkstream=True)
        except redis.ResponseError:
            pass

        msgs = self.r.xreadgroup(
            group, consumer, {stream: ">"}, count=count, block=block
        )
        if not msgs:
            return None

        stream_name, entries = msgs[0]
        msg_id, payload = entries[0]
        data = _decode(json.loads(payload[b"data"]))
        self.r.xack(stream, group, msg_id)
        return data
