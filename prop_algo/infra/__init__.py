"""Infra helpers.

Metrics pulls in prometheus_client; keep that import lazy so Stream-only
callers (and unit tests) do not require the metrics stack at import time.
"""

from .stream import Stream

__all__ = ["Stream", "Metrics"]


def __getattr__(name: str):
    if name == "Metrics":
        from .metrics import Metrics

        return Metrics
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
