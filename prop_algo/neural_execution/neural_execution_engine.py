"""Neural / heuristic execution advice engine (torch optional)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

from .model_loader import load_model
from .route_predictor import RoutePredictor
from .sizing_model import SizingModel
from .slippage_model import SlippageModel
from .volatility_model import VolatilityModel


def _env_flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


class NeuralExecutionEngine:
    def __init__(
        self,
        route_model: RoutePredictor,
        slip_model: SlippageModel,
        vol_model: VolatilityModel,
        size_model: SizingModel,
        backend: str = "heuristic",
    ):
        self.route_model = route_model
        self.slip_model = slip_model
        self.vol_model = vol_model
        self.size_model = size_model
        self.backend = backend

    def run(
        self,
        market_features: Sequence[Any],
        risk_features: Sequence[Any],
        gov_features: Sequence[Any],
    ) -> dict[str, Any]:
        features = list(market_features or []) + list(risk_features or []) + list(
            gov_features or []
        )

        route = self.route_model.predict(features)
        slippage = self.slip_model.predict(features)
        volatility = self.vol_model.predict(features)
        size = self.size_model.predict(features)

        return {
            "route": route,
            "slippage": slippage,
            "volatility": volatility,
            "size": size,
            "backend": self.backend,
        }

    @classmethod
    def build(
        cls,
        model_dir: str | Path | None = None,
        *,
        route_path: str | None = None,
        slip_path: str | None = None,
        vol_path: str | None = None,
        size_path: str | None = None,
    ) -> "NeuralExecutionEngine":
        """Construct an engine; missing torch/models → heuristic predictors."""
        root = Path(model_dir) if model_dir else None
        if root is None:
            env_dir = os.environ.get("NEURAL_MODEL_DIR", "").strip()
            root = Path(env_dir) if env_dir else None

        def _resolve(explicit: str | None, filename: str) -> str | None:
            if explicit:
                return explicit
            if root is not None:
                return str(root / filename)
            return None

        route_m = load_model(_resolve(route_path, "route.pt"))
        slip_m = load_model(_resolve(slip_path, "slippage.pt"))
        vol_m = load_model(_resolve(vol_path, "volatility.pt"))
        size_m = load_model(_resolve(size_path, "sizing.pt"))

        loaded = sum(m is not None for m in (route_m, slip_m, vol_m, size_m))
        backend = "torch" if loaded == 4 else ("mixed" if loaded else "heuristic")

        return cls(
            RoutePredictor(route_m),
            SlippageModel(slip_m),
            VolatilityModel(vol_m),
            SizingModel(size_m),
            backend=backend,
        )

    @classmethod
    def enabled(cls) -> bool:
        """``NEURAL_EXECUTION=1`` enables the optional neural step (default on)."""
        return _env_flag("NEURAL_EXECUTION", "1")
