"""Route selection: torch model when available, else deterministic heuristic."""

from __future__ import annotations

from typing import Any, Sequence

ROUTES = ("MARKET", "LIMIT", "VWAP")


def _as_floats(features: Sequence[Any]) -> list[float]:
    out: list[float] = []
    for v in features or ():
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(0.0)
    return out


class RoutePredictor:
    def __init__(self, model: Any | None = None):
        self.model = model

    def predict(self, features: Sequence[Any]) -> str:
        if self.model is not None:
            try:
                return self._predict_torch(features)
            except Exception:
                pass
        return self._predict_heuristic(features)

    def _predict_torch(self, features: Sequence[Any]) -> str:
        import torch
        import torch.nn.functional as F

        x = torch.tensor(_as_floats(features), dtype=torch.float32)
        logits = self.model(x)
        probs = F.softmax(logits, dim=-1)
        return ROUTES[int(torch.argmax(probs))]

    def _predict_heuristic(self, features: Sequence[Any]) -> str:
        vals = _as_floats(features)
        score = sum(vals) / max(len(vals), 1)
        if score < 0.35:
            return "LIMIT"
        if score > 1.2:
            return "VWAP"
        return "MARKET"
