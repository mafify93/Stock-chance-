"""Loads and runs the trained ML direction model.

The model itself is trained offline by `backend/scripts/train_ml_model.py`
and saved to `model.joblib` in this directory (not committed - see
.gitignore). If that file doesn't exist, `MLPredictor.predict` returns
`None` and callers fall back to the rule-based signal only - the ML
prediction is an enhancement, not a requirement.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from ..indicators import compute_all_indicators
from .features import build_feature_frame

logger = logging.getLogger(__name__)

_data_dir = os.environ.get("PERSISTENT_DATA_DIR")
_persistent_path = Path(_data_dir) / "model.joblib" if _data_dir else None
_default_path = Path(__file__).resolve().parent / "model.joblib"
MODEL_PATH = _persistent_path if (_persistent_path and _persistent_path.exists()) else _default_path


def _score_to_action(score: float) -> str:
    if score >= 0.5:
        return "STRONG_BUY"
    if score >= 0.15:
        return "BUY"
    if score <= -0.5:
        return "STRONG_SELL"
    if score <= -0.15:
        return "SELL"
    return "HOLD"


class MLPredictor:
    """Lazily loads a trained gradient-boosting classifier that predicts the
    probability the price will be higher in N trading days, expressed as a
    -1..+1 score alongside the rule-based signal engine."""

    def __init__(self, model_path: Path = MODEL_PATH):
        self._model_path = model_path
        self._model = None
        self._metadata: dict = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._model_path.exists():
            logger.info("No ML model found at %s - ML predictions disabled", self._model_path)
            return
        try:
            import joblib

            bundle = joblib.load(self._model_path)
            self._model = bundle["model"]
            self._metadata = bundle.get("metadata", {})
        except Exception:  # noqa: BLE001
            logger.exception("Failed to load ML model from %s", self._model_path)
            self._model = None

    @property
    def available(self) -> bool:
        self._load()
        return self._model is not None

    def predict(self, df: pd.DataFrame) -> dict | None:
        """Returns a dict with `probability_up`, `score`, `action`,
        `confidence`, `horizon_days`, `model_version`, or `None` if no
        trained model is available or prediction fails."""
        self._load()
        if self._model is None:
            return None

        try:
            data = compute_all_indicators(df)
            features = build_feature_frame(data)
            last = features.iloc[[-1]]
            probability_up = float(self._model.predict_proba(last)[0][1])
        except Exception:  # noqa: BLE001
            logger.exception("ML prediction failed")
            return None

        score = round((probability_up - 0.5) * 2, 4)
        return {
            "probability_up": round(probability_up, 4),
            "score": score,
            "action": _score_to_action(score),
            "confidence": round(min(100.0, abs(probability_up - 0.5) * 200), 1),
            "horizon_days": self._metadata.get("horizon_days", 5),
            "model_version": self._metadata.get("version"),
        }


ml_predictor = MLPredictor()
