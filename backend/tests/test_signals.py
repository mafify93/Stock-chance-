import numpy as np
import pandas as pd
import pytest

from app.signals import analyze


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


def test_analyze_returns_valid_action():
    df = _trending_df(drift=0.5)
    result = analyze("TEST", df)
    assert result.symbol == "TEST"
    assert result.action in {"STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"}
    assert -1.0 <= result.score <= 1.0
    assert 0 <= result.confidence <= 100
    assert result.price > 0
    assert len(result.reasons) > 0


def test_strong_uptrend_does_not_skew_bearish():
    df = _trending_df(drift=1.2, seed=7)
    result = analyze("UP", df)
    # A sustained strong uptrend may also be overbought (mean-reversion
    # votes), but the composite signal should never flip to outright bearish.
    assert result.action not in {"SELL", "STRONG_SELL"}


def test_strong_downtrend_does_not_skew_bullish():
    df = _trending_df(drift=-1.2, seed=7)
    result = analyze("DOWN", df)
    # A sustained strong downtrend may also be oversold (mean-reversion
    # votes), but the composite signal should never flip to outright bullish.
    assert result.action not in {"BUY", "STRONG_BUY"}


def test_levels_present_for_directional_signal():
    df = _trending_df(drift=1.2, seed=7)
    result = analyze("UP", df)
    assert "suggested_entry" in result.levels
    assert "stop_loss" in result.levels
    assert "take_profit" in result.levels
    assert result.levels["stop_loss"] < result.price < result.levels["take_profit"]


def test_empty_dataframe_raises():
    df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    with pytest.raises(ValueError):
        analyze("EMPTY", df)


def test_insufficient_history_raises():
    df = _trending_df(n=5)
    with pytest.raises(ValueError):
        analyze("SHORT", df)
