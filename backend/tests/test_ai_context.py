import numpy as np
import pandas as pd

from app import ai_context, models


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


def test_symbol_snapshot_returns_signal_and_ml(monkeypatch):
    monkeypatch.setattr(ai_context.yahoo, "get_history", lambda *a, **k: _trending_df())
    monkeypatch.setattr(
        ai_context.ml_predictor,
        "predict",
        lambda df: {"probability_up": 0.65, "score": 0.3, "action": "BUY", "confidence": 65, "horizon_days": 5, "model_version": "v1"},
    )

    snap = ai_context.symbol_snapshot("AAPL")
    assert snap is not None
    assert snap["symbol"] == "AAPL"
    assert snap["signal"] in ("STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL")
    assert snap["ml_probability_up"] == 0.65
    assert len(snap["reasons"]) <= 3


def test_symbol_snapshot_returns_none_on_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no data")

    monkeypatch.setattr(ai_context.yahoo, "get_history", boom)
    assert ai_context.symbol_snapshot("ZZZZ") is None


def test_auto_trader_summary_shape(monkeypatch):
    status = models.AutoTraderStatus(
        config=models.AutoTraderConfig(
            enabled=True,
            broker="alpaca",
            symbols=["AAPL"],
            auto_select=False,
            auto_select_count=5,
            max_open_positions=5,
            min_confidence=70.0,
            max_position_value=100.0,
            max_daily_trades=3,
            poll_interval_minutes=15,
            environment="paper",
            confirmed_real_money=False,
            alpaca_configured=True,
            questrade_configured=False,
        ),
        last_run_at="2026-06-15T08:00:00+00:00",
        trades_today=1,
        decisions=[
            models.AutoTraderDecision(
                timestamp="2026-06-15T08:00:00+00:00",
                symbol="AAPL",
                action="BUY",
                combined_confidence=80.0,
                executed=True,
                reason="placed buy order for 1 AAPL",
                order_id="123",
            )
        ],
    )
    monkeypatch.setattr(ai_context.auto_trader, "get_status", lambda: status)

    summary = ai_context.auto_trader_summary()
    assert summary["enabled"] is True
    assert summary["trades_today"] == 1
    assert summary["recent_decisions"][0]["symbol"] == "AAPL"
    assert summary["recent_decisions"][0]["executed"] is True


def test_dedupe_symbols():
    result = ai_context.dedupe_symbols(["aapl", "MSFT"], ["msft", "tsla"], limit=10)
    assert result == ["AAPL", "MSFT", "TSLA"]


def test_dedupe_symbols_respects_limit():
    result = ai_context.dedupe_symbols(["a", "b", "c", "d"], limit=2)
    assert result == ["A", "B"]
