"""Self-improving trade learner.

Every time a trade closes, we record the features that were present at entry
alongside the outcome (win / loss / scratch). A RandomForestClassifier trains
on this growing history to estimate the win probability for future setups.

How it influences trading
─────────────────────────
The learner's win_probability() score is used as a confidence multiplier in
the engine. A trade the model thinks has a 70% win chance gets a confidence
boost; a trade it thinks has a 30% chance gets suppressed below the minimum
threshold and is skipped.

    effective_confidence = raw_confidence × (0.4 + 1.2 × win_probability)

At win_prob = 0.50 (neutral / no data): multiplier = 1.0 — no change.
At win_prob = 0.70 (model likes it):    multiplier = 1.24 — small boost.
At win_prob = 0.30 (model dislikes it): multiplier = 0.76 — suppressed.

Design constraints
──────────────────
- Needs at least MIN_TRADES closed trades before activating (avoids acting
  on noise from a handful of results).
- Retrains every RETRAIN_EVERY new trades so it adapts to changing markets.
- Uses shallow RandomForest (max_depth=4) to limit overfitting on small samples.
- Persists trade history to disk (STATE_DIR) so learning survives restarts.
- Never crashes the engine — every public method catches its own exceptions.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from threading import Lock

log = logging.getLogger(__name__)

# Encode pairs as integers so sklearn can use them as features.
_PAIR_IDS: dict[str, float] = {
    "EUR_USD": 0.0,
    "GBP_USD": 1.0,
    "USD_JPY": 2.0,
    "EUR_JPY": 3.0,
    "GBP_JPY": 4.0,
}

_SIGNAL_IDS: dict[str, float] = {
    "ema_vwap_rsi": 0.0,
    "london_breakout": 1.0,
    "ict_sweep": 2.0,
    "orb": 3.0,
    "silver_bullet": 4.0,
    "order_block": 5.0,
}


@dataclass
class TradeFeatures:
    """Snapshot of signal conditions captured at trade entry.

    Stored as a dict on TradeRecord so it survives state persistence.
    All values are floats so sklearn can consume them directly.
    """
    pair: str           # e.g. "EUR_USD"
    side: str           # "long" | "short"
    confidence: float   # raw signal confidence 0–100
    stop_pips: float    # planned stop distance in pips
    spread_pips: float  # bid-ask spread at entry
    atr_pips: float     # ATR(14) of M5 bars at entry — measures market volatility
    hour_utc: int       # UTC hour of entry (0–23) — captures session timing
    signal_type: str    # "ema_vwap_rsi" | "london_breakout"

    def to_vector(self) -> list[float]:
        """Feature vector fed to the classifier. Order must never change."""
        return [
            _PAIR_IDS.get(self.pair, -1.0),
            1.0 if self.side == "long" else 0.0,
            self.confidence / 100.0,
            min(self.stop_pips, 50.0) / 50.0,   # normalise to 0–1
            min(self.spread_pips, 5.0) / 5.0,
            min(self.atr_pips, 30.0) / 30.0,
            self.hour_utc / 23.0,
            _SIGNAL_IDS.get(self.signal_type, 0.0),
        ]

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "TradeFeatures":
        return TradeFeatures(**{k: d[k] for k in TradeFeatures.__dataclass_fields__})


class TradeLearner:
    """RandomForest-based self-improving entry filter."""

    MIN_TRADES = 20     # minimum closed trades before the model activates
    RETRAIN_EVERY = 5   # retrain after every N new completed trades

    def __init__(self, state_dir: str) -> None:
        self._lock = Lock()
        self._history_path = os.path.join(state_dir, "trade_learner.json")
        # Each entry: {"features": [...float...], "won": 0|1}
        self._history: list[dict] = []
        self._model = None          # sklearn RandomForestClassifier, or None
        self._pending_retrain = 0   # trades since last retrain
        self._load()

    # ── Public API ───────────────────────────────────────────────────────────

    def record(self, features: TradeFeatures, realized_pl: float) -> None:
        """Call when a trade closes. realized_pl > 0 = win, < 0 = loss, 0 = scratch."""
        if realized_pl == 0:
            return  # scratch trades are uninformative — skip

        won = 1 if realized_pl > 0 else 0
        entry = {"features": features.to_vector(), "won": won}

        with self._lock:
            self._history.append(entry)
            self._pending_retrain += 1
            self._save()
            if (len(self._history) >= self.MIN_TRADES
                    and self._pending_retrain >= self.RETRAIN_EVERY):
                self._retrain()
                self._pending_retrain = 0

        wins = sum(e["won"] for e in self._history)
        log.info(
            f"TradeLearner: recorded {'WIN' if won else 'LOSS'} — "
            f"history: {len(self._history)} trades, "
            f"{wins}/{len(self._history)} wins ({wins/len(self._history):.0%})"
        )

    def confidence_multiplier(self, features: TradeFeatures) -> float:
        """Return a multiplier (0.5–1.5) to apply to raw signal confidence.

        Neutral (1.0) when the model has no opinion (insufficient data).
        Above 1.0 for setups the model likes; below 1.0 for setups it dislikes.
        """
        win_prob = self._win_probability(features)
        # Linear mapping: prob=0.5 → 1.0, prob=0.7 → 1.24, prob=0.3 → 0.76
        return round(0.4 + 1.2 * win_prob, 3)

    def stats(self) -> dict:
        """Summary stats for the /status endpoint."""
        with self._lock:
            total = len(self._history)
            if total == 0:
                return {
                    "total_trades_observed": 0,
                    "win_rate": 0.0,
                    "model_active": False,
                    "trades_until_active": self.MIN_TRADES,
                    "feature_importances": None,
                }
            wins = sum(e["won"] for e in self._history)
            importances = None
            if self._model is not None:
                try:
                    names = [
                        "pair", "side", "confidence", "stop_pips",
                        "spread_pips", "atr_pips", "hour_utc", "signal_type",
                    ]
                    importances = {
                        names[i]: round(float(v), 4)
                        for i, v in enumerate(self._model.feature_importances_)
                        if i < len(names)
                    }
                except Exception:
                    pass
            return {
                "total_trades_observed": total,
                "win_rate": round(wins / total, 3),
                "model_active": self._model is not None,
                "trades_until_active": max(0, self.MIN_TRADES - total),
                "feature_importances": importances,
            }

    # ── Private ──────────────────────────────────────────────────────────────

    def _win_probability(self, features: TradeFeatures) -> float:
        with self._lock:
            if self._model is None:
                return 0.5  # neutral until enough data
            try:
                import numpy as np
                vec = np.array([features.to_vector()])
                return float(self._model.predict_proba(vec)[0][1])
            except Exception as exc:
                log.debug(f"TradeLearner: predict failed: {exc}")
                return 0.5

    def _retrain(self) -> None:
        try:
            import numpy as np
            from sklearn.ensemble import RandomForestClassifier

            X = [e["features"] for e in self._history]
            y = [e["won"] for e in self._history]

            clf = RandomForestClassifier(
                n_estimators=200,
                max_depth=4,            # shallow = less overfitting on small datasets
                min_samples_leaf=3,     # each leaf needs at least 3 examples
                class_weight="balanced", # handle win/loss imbalance
                random_state=42,
            )
            clf.fit(X, y)
            self._model = clf

            wins = sum(y)
            log.info(
                f"TradeLearner: model retrained on {len(y)} trades "
                f"({wins} wins / {len(y)-wins} losses, {wins/len(y):.0%} win rate)"
            )

            # Log feature importances so we can see what the model learned
            feature_names = [
                "pair", "side", "confidence", "stop_pips",
                "spread_pips", "atr_pips", "hour_utc", "signal_type",
            ]
            importances = clf.feature_importances_
            ranked = sorted(zip(feature_names, importances), key=lambda x: -x[1])
            log.info(
                "TradeLearner: top predictors — "
                + ", ".join(f"{n}: {v:.2f}" for n, v in ranked[:4])
            )

        except ImportError:
            log.warning(
                "TradeLearner: scikit-learn not installed — "
                "add scikit-learn to requirements.txt to enable AI learning"
            )
        except Exception as exc:
            log.warning(f"TradeLearner: retrain failed: {exc}")

    def reset(self) -> int:
        """Wipe all learned history and the trained model, returning to a neutral
        (untrained) state. Returns the number of trades that were discarded.

        Use after a change that invalidates past outcomes (e.g. the cross-pair
        sizing fix) so the model relearns only from correctly-sized trades.
        """
        with self._lock:
            discarded = len(self._history)
            self._history = []
            self._model = None
            self._pending_retrain = 0
            self._save()  # persist the empty history so the reset survives restarts
        log.info(f"TradeLearner: reset — discarded {discarded} historical trades")
        return discarded

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._history_path) or ".", exist_ok=True)
            with open(self._history_path, "w") as f:
                json.dump(self._history, f)
        except Exception as exc:
            log.debug(f"TradeLearner: save failed (non-fatal): {exc}")

    def _load(self) -> None:
        try:
            if not os.path.exists(self._history_path):
                return
            with open(self._history_path) as f:
                self._history = json.load(f)
            if len(self._history) >= self.MIN_TRADES:
                self._retrain()
            log.info(f"TradeLearner: loaded {len(self._history)} historical trades from disk")
        except Exception as exc:
            log.debug(f"TradeLearner: load failed, starting fresh: {exc}")


# ── Module-level singleton initialised when the engine first imports this ───
import os as _os

_state_dir = _os.environ.get(
    "STATE_DIR",
    _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..", ".botstate")),
)
trade_learner = TradeLearner(_state_dir)
