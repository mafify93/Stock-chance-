"""Trains the ML direction model used by /api/signal and /api/ai/analysis.

Fetches several years of daily history for the default stock universe from
Yahoo Finance, builds technical-indicator features (see
`app.ml.features`), and trains a gradient-boosting classifier to predict
whether each symbol's price will be higher `HORIZON_DAYS` trading days
later. The trained model is saved to `app/ml/model.joblib`, which
`MLPredictor` loads lazily at request time.

This is an offline, manual step - re-run it periodically (e.g. monthly) to
retrain on fresh data:

    cd backend
    pip install -r requirements.txt
    python -m scripts.train_ml_model

Takes a few minutes depending on universe size and network speed. A test
accuracy meaningfully above ~52-55% on 5-day-ahead direction would already be
notable for this kind of model - don't expect "state of the art" miracle
numbers from public daily OHLCV data alone.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.indicators import compute_all_indicators  # noqa: E402
from app.ml.features import FEATURE_NAMES, build_feature_frame, build_labels  # noqa: E402
from app.providers import yahoo  # noqa: E402
from app.universe import DEFAULT_UNIVERSE  # noqa: E402

HORIZON_DAYS = 5
HISTORY_PERIOD = "5y"
MIN_ROWS = 250
MODEL_PATH = Path(__file__).resolve().parents[1] / "app" / "ml" / "model.joblib"


def build_dataset(symbols: list[str]) -> pd.DataFrame:
    frames = []
    for symbol in symbols:
        try:
            df = yahoo.get_history(symbol, period=HISTORY_PERIOD, interval="1d")
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {symbol}: {exc}")
            continue
        if len(df) < MIN_ROWS:
            print(f"  skip {symbol}: not enough history ({len(df)} rows)")
            continue

        data = compute_all_indicators(df)
        features = build_feature_frame(data)
        labels = build_labels(data, horizon=HORIZON_DAYS)

        frame = features.copy()
        frame["label"] = labels
        frame["date"] = data.index
        frame = frame.dropna(subset=["label"])
        frames.append(frame)
        print(f"  {symbol}: {len(frame)} rows")

    if not frames:
        raise RuntimeError("No usable data fetched for any symbol")
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    print(f"Building dataset from {len(DEFAULT_UNIVERSE)} symbols (this takes a while)...")
    dataset = build_dataset(DEFAULT_UNIVERSE)
    print(f"Total rows: {len(dataset)}")

    # Time-based split (not random) to avoid leaking future data into training.
    dataset = dataset.sort_values("date")
    split = int(len(dataset) * 0.85)
    train, test = dataset.iloc[:split], dataset.iloc[split:]

    x_train, y_train = train[FEATURE_NAMES], train["label"]
    x_test, y_test = test[FEATURE_NAMES], test["label"]

    model = HistGradientBoostingClassifier(
        max_iter=200,
        learning_rate=0.05,
        max_depth=4,
        random_state=42,
    )
    model.fit(x_train, y_train)

    train_acc = accuracy_score(y_train, model.predict(x_train))
    test_acc = accuracy_score(y_test, model.predict(x_test))
    print(f"Train accuracy: {train_acc:.3f}")
    print(f"Test accuracy:  {test_acc:.3f}  (a naive always-up baseline is typically ~0.50-0.55)")

    metadata = {
        "version": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
        "horizon_days": HORIZON_DAYS,
        "feature_names": FEATURE_NAMES,
        "train_accuracy": round(float(train_acc), 4),
        "test_accuracy": round(float(test_acc), 4),
        "train_rows": len(train),
        "test_rows": len(test),
        "symbols": DEFAULT_UNIVERSE,
    }

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "metadata": metadata}, MODEL_PATH)
    print(f"Saved model to {MODEL_PATH}")


if __name__ == "__main__":
    main()
