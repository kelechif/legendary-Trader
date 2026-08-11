"""Position size: torch model when available, else heuristic."""

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


class SizingModel:
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
        # Prefer risk budget (first risk feature when present) to scale size.
        risk = vals[0] if vals else 1.0
        risk = max(0.0, min(1.0, risk))
        return float(max(0.01, min(1.0, 0.1 * (0.5 + risk))))
