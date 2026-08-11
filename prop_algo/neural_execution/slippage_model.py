"""Slippage estimate: torch model when available, else heuristic."""

from __future__ import annotations

from typing import Any, Sequence


def _as_floats(features: Sequence[Any]) -> list[float]:
    out: list[float] = []
    for v in features or ():
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(0.0)
    return out


class SlippageModel:
    def __init__(self, model: Any | None = None):
        self.model = model

    def predict(self, features: Sequence[Any]) -> float:
        if self.model is not None:
            try:
                return self._predict_torch(features)
            except Exception:
                pass
        return self._predict_heuristic(features)

    def _predict_torch(self, features: Sequence[Any]) -> float:
        import torch

        x = torch.tensor(_as_floats(features), dtype=torch.float32)
        return float(self.model(x))

    def _predict_heuristic(self, features: Sequence[Any]) -> float:
        vals = _as_floats(features)
        # Base 5 bps + mild sensitivity to feature magnitude.
        mag = sum(abs(v) for v in vals) / max(len(vals), 1)
        return float(max(0.0001, min(0.01, 0.0005 + 0.0002 * mag)))
