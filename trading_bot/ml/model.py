from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score

from trading_bot.features.indicators import add_all_indicators, build_feature_matrix
from trading_bot.logger import get_logger

logger = get_logger(__name__)

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"


@dataclass
class TrainResult:
    train_accuracy: float
    test_accuracy: float
    test_precision: float
    n_train: int
    n_test: int


def make_labels(df: pd.DataFrame, lookahead_bars: int, up_threshold_pct: float) -> pd.Series:
    forward_return = df["close"].shift(-lookahead_bars) / df["close"] - 1
    return (forward_return > up_threshold_pct).astype(int)


class DirectionModel:
    """Predicts the probability that price will be higher N bars from now."""

    def __init__(
        self,
        model_type: str = "random_forest",
        n_estimators: int = 300,
        max_depth: int = 6,
        lookahead_bars: int = 1,
        up_threshold_pct: float = 0.0,
        train_test_split: float = 0.8,
        random_state: int = 42,
    ):
        self.model_type = model_type
        self.lookahead_bars = lookahead_bars
        self.up_threshold_pct = up_threshold_pct
        self.train_test_split = train_test_split
        self.feature_columns: list[str] | None = None

        if model_type == "gradient_boosting":
            self.model = GradientBoostingClassifier(
                n_estimators=n_estimators, max_depth=max_depth, random_state=random_state
            )
        else:
            self.model = RandomForestClassifier(
                n_estimators=n_estimators,
                max_depth=max_depth,
                random_state=random_state,
                n_jobs=-1,
                class_weight="balanced",
            )

    def _prepare(self, raw_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        enriched = add_all_indicators(raw_df)
        features = build_feature_matrix(enriched)
        labels = make_labels(enriched, self.lookahead_bars, self.up_threshold_pct)

        data = features.copy()
        data["label"] = labels
        data = data.dropna()
        return data.drop(columns=["label"]), data["label"]

    def train(self, raw_df: pd.DataFrame) -> TrainResult:
        X, y = self._prepare(raw_df)
        if len(X) < 50:
            raise ValueError("Not enough clean historical rows to train a model (need >= 50).")

        self.feature_columns = list(X.columns)
        split_idx = int(len(X) * self.train_test_split)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        self.model.fit(X_train, y_train)

        train_pred = self.model.predict(X_train)
        result = TrainResult(
            train_accuracy=accuracy_score(y_train, train_pred),
            test_accuracy=0.0,
            test_precision=0.0,
            n_train=len(X_train),
            n_test=len(X_test),
        )

        if len(X_test) > 0:
            test_pred = self.model.predict(X_test)
            result.test_accuracy = accuracy_score(y_test, test_pred)
            result.test_precision = precision_score(y_test, test_pred, zero_division=0)

        logger.info(
            "Trained %s | train_acc=%.3f test_acc=%.3f test_prec=%.3f (n_train=%d n_test=%d)",
            self.model_type,
            result.train_accuracy,
            result.test_accuracy,
            result.test_precision,
            result.n_train,
            result.n_test,
        )
        return result

    def predict_latest(self, raw_df: pd.DataFrame) -> dict[str, Any]:
        """Predict direction probability for the most recent bar in raw_df."""
        if self.feature_columns is None:
            raise RuntimeError("Model has not been trained or loaded yet.")

        enriched = add_all_indicators(raw_df)
        features = build_feature_matrix(enriched)[self.feature_columns]
        latest = features.dropna().iloc[[-1]]

        proba_up = float(self.model.predict_proba(latest)[0][1])
        return {
            "date": latest.index[-1],
            "probability_up": proba_up,
            "probability_down": 1 - proba_up,
        }

    def save(self, symbol: str, model_dir: Path = MODEL_DIR) -> Path:
        model_dir.mkdir(exist_ok=True)
        path = model_dir / f"{self._safe_name(symbol)}.joblib"
        joblib.dump(
            {
                "model": self.model,
                "feature_columns": self.feature_columns,
                "model_type": self.model_type,
                "lookahead_bars": self.lookahead_bars,
                "up_threshold_pct": self.up_threshold_pct,
            },
            path,
        )
        logger.info("Saved model for %s -> %s", symbol, path)
        return path

    @classmethod
    def load(cls, symbol: str, model_dir: Path = MODEL_DIR) -> "DirectionModel":
        path = model_dir / f"{cls._safe_name(symbol)}.joblib"
        payload = joblib.load(path)
        instance = cls(
            model_type=payload["model_type"],
            lookahead_bars=payload["lookahead_bars"],
            up_threshold_pct=payload["up_threshold_pct"],
        )
        instance.model = payload["model"]
        instance.feature_columns = payload["feature_columns"]
        return instance

    @staticmethod
    def _safe_name(symbol: str) -> str:
        return symbol.replace("=", "_").replace("^", "").replace("/", "_")
