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


class Stream:
    def __init__(self, host=None, port=None):
        host = host if host is not None else os.getenv("REDIS_HOST", "redis")
        port = int(port if port is not None else os.getenv("REDIS_PORT", "6379"))
        self.r = redis.Redis(host=host, port=port)

    def publish(self, stream, data):
        self.r.xadd(stream, {"data": json.dumps(_encode(data))})

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
