"""Unit tests for neural_execution heuristic / fallback path (no torch required)."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from prop_algo.neural_execution import (
    NeuralExecutionEngine,
    RoutePredictor,
    SizingModel,
    SlippageModel,
    VolatilityModel,
    load_model,
)


class TestNeuralExecutionFallback(unittest.TestCase):
    def test_load_model_missing_path_returns_none(self):
        self.assertIsNone(load_model(None))
        self.assertIsNone(load_model(""))
        self.assertIsNone(load_model("/nonexistent/path/route.pt"))

    def test_build_without_models_uses_heuristic_backend(self):
        engine = NeuralExecutionEngine.build(model_dir="/nonexistent/models")
        self.assertEqual(engine.backend, "heuristic")
        out = engine.run([1.0, 0.5], [0.8, 0.0, 0.5], [1.0, 0.0])
        self.assertIn(out["route"], ("MARKET", "LIMIT", "VWAP"))
        self.assertIsInstance(out["slippage"], float)
        self.assertIsInstance(out["volatility"], float)
        self.assertIsInstance(out["size"], float)
        self.assertGreater(out["size"], 0.0)
        self.assertEqual(out["backend"], "heuristic")

    def test_predictors_work_with_none_model(self):
        self.assertEqual(RoutePredictor(None).predict([1.0]), "MARKET")
        self.assertGreater(SlippageModel(None).predict([1.0]), 0.0)
        self.assertGreater(VolatilityModel(None).predict([1.0]), 0.0)
        self.assertGreater(SizingModel(None).predict([1.0]), 0.0)

    def test_enabled_env_flag(self):
        with mock.patch.dict(os.environ, {"NEURAL_EXECUTION": "0"}, clear=False):
            self.assertFalse(NeuralExecutionEngine.enabled())
        with mock.patch.dict(os.environ, {"NEURAL_EXECUTION": "1"}, clear=False):
            self.assertTrue(NeuralExecutionEngine.enabled())


if __name__ == "__main__":
    unittest.main()
