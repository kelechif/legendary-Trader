"""Compatibility re-export — prefer `from infra.stream import Stream`."""

try:
    from infra.stream import Stream
except ImportError:  # package import as prop_algo.* (pytest / non-Docker)
    from prop_algo.infra.stream import Stream

__all__ = ["Stream"]
