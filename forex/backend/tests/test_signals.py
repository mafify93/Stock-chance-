import pytest

from app.signals import analyze


def test_uptrend_is_bullish(uptrend_h1):
    result = analyze("EUR_USD", uptrend_h1)
    assert result.action in ("BUY", "STRONG_BUY")
    assert result.score > 0
    assert result.pair == "EUR_USD"
    assert result.reasons


def test_levels_are_in_pips(uptrend_h1):
    result = analyze("EUR_USD", uptrend_h1)
    assert "stop_pips" in result.levels
    assert "target_pips" in result.levels
    # Risk/reward is 2:1 by construction.
    assert result.levels["target_pips"] == pytest.approx(result.levels["stop_pips"] * 2, rel=0.01)


def test_empty_df_raises():
    import pandas as pd

    with pytest.raises(ValueError):
        analyze("EUR_USD", pd.DataFrame())
