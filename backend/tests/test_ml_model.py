import numpy as np
import pandas as pd

from app.indicators import compute_all_indicators
from app.ml.features import FEATURE_NAMES, build_feature_frame, build_labels
from app.ml.model import MLPredictor


def _trending_df(n=300, drift=0.3, seed=1):
    rng = np.random.default_rng(seed)
    base = 100 + np.cumsum(drift + rng.normal(0, 1, n))
    high = base + rng.uniform(0, 1, n)
    low = base - rng.uniform(0, 1, n)
    close = base
    open_ = base + rng.normal(0, 0.5, n)
    volume = rng.uniform(1e6, 5e6, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}, index=idx)


def test_build_feature_frame_has_expected_columns():
    df = _trending_df()
    data = compute_all_indicators(df)
    features = build_feature_frame(data)
    assert list(features.columns) == FEATURE_NAMES
    assert len(features) == len(df)
    # Early rows lack enough history for sma_200 etc - NaNs are expected and
    # left for the tree model to handle natively.
    assert features["price_vs_sma200"].iloc[:199].isna().all()
    assert features["price_vs_sma200"].iloc[-1] is not None


def test_build_labels_marks_future_direction():
    df = _trending_df(drift=1.0)
    data = compute_all_indicators(df)
    labels = build_labels(data, horizon=5)
    assert len(labels) == len(df)
    # Last 5 rows have no future close to compare against.
    assert labels.iloc[-5:].isna().all()
    # A strong uptrend should mostly label "up".
    assert labels.dropna().mean() > 0.5


def test_predictor_unavailable_without_model_file(tmp_path):
    predictor = MLPredictor(model_path=tmp_path / "missing.joblib")
    assert predictor.available is False
    assert predictor.predict(_trending_df()) is None


def test_predictor_returns_prediction_for_trained_model(tmp_path):
    import joblib
    from sklearn.ensemble import HistGradientBoostingClassifier

    # Train a tiny model on synthetic data so predict_proba has 2 classes.
    df = _trending_df(n=400, drift=0.5)
    data = compute_all_indicators(df)
    features = build_feature_frame(data)
    labels = build_labels(data, horizon=5)
    mask = labels.notna()

    model = HistGradientBoostingClassifier(max_iter=20, random_state=0)
    model.fit(features[mask], labels[mask])

    model_path = tmp_path / "model.joblib"
    joblib.dump({"model": model, "metadata": {"horizon_days": 5, "version": "test"}}, model_path)

    predictor = MLPredictor(model_path=model_path)
    assert predictor.available is True

    result = predictor.predict(df)
    assert result is not None
    assert 0.0 <= result["probability_up"] <= 1.0
    assert -1.0 <= result["score"] <= 1.0
    assert result["action"] in {"STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"}
    assert 0 <= result["confidence"] <= 100
    assert result["horizon_days"] == 5
    assert result["model_version"] == "test"
