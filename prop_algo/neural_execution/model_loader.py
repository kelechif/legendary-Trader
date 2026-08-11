"""Optional torch model loader — never hard-requires torch at import time."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_model(path: str | Path | None) -> Any | None:
    """Load a torch model from ``path``.

    Returns ``None`` when torch is unavailable, the path is missing, or load fails.
    """
    if not path:
        return None
    try:
        import torch
    except ImportError:
        return None

    p = Path(path)
    if not p.is_file():
        return None
    try:
        try:
            model = torch.load(str(p), map_location="cpu", weights_only=False)
        except TypeError:
            model = torch.load(str(p), map_location="cpu")
        if hasattr(model, "eval"):
            model.eval()
        return model
    except Exception:
        return None
