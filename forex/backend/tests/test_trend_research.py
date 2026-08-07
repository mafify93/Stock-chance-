"""Unit tests for the higher-timeframe trend-research harness."""
import numpy as np
import pandas as pd

from app.autotrader.trend_research import TrendParams, run_trend_research, simulate_trend


def _df_from_closes(closes):
    """Build an OHLCV frame from a close series (H/L padded around close)."""
    idx = pd.date_range("2020-01-01", periods=len(closes), freq="4h", tz="UTC")
    c = pd.Series(closes, index=idx)
    return pd.DataFrame({
        "Open": c.shift(1).fillna(c.iloc[0]),
        "High": c * 1.001,
        "Low": c * 0.999,
        "Close": c,
        "Volume": 1000,
    })


def test_sustained_uptrend_is_profitable():
    # Uptrend then reversal so the long actually closes (channel/stop exit)
    # and books its profit — a monotonic ramp never triggers an exit.
    up = list(1.0 + np.linspace(0, 0.5, 450))       # +50% ramp
    down = list(1.5 - np.linspace(0, 0.5, 150))     # sharp reversal (steeper than
                                                    # intrabar range) to force the exit
    df = _df_from_closes(up + down)
    p = TrendParams(entry_n=20, exit_n=10, atr_n=14, ma_n=50, spread_pips=1.0)
    res = simulate_trend(df, "EUR_USD", p)
    assert res["trades"] >= 1
    assert res["return_pct"] > 0
    assert res["expectancy_r"] > 0


def test_choppy_flat_market_does_not_run_away():
    # Pure noise around a flat mean: a trend-follower should NOT be strongly
    # profitable (it should bleed small or hover near zero, not print an edge).
    rng = np.random.default_rng(42)
    closes = list(1.0 + np.cumsum(rng.normal(0, 0.0005, 600)) * 0.0)  # flat
    closes = [1.0 + 0.001 * np.sin(i / 5) for i in range(600)]        # oscillating
    df = _df_from_closes(closes)
    p = TrendParams(entry_n=20, exit_n=10, atr_n=14, ma_n=50, spread_pips=1.0)
    res = simulate_trend(df, "EUR_USD", p)
    # Not asserting a loss (noise varies), only that it doesn't fabricate a huge edge.
    assert res["return_pct"] < 15


def test_concentration_metric_present_and_walk_forward():
    closes = list(1.0 + np.linspace(0, 0.5, 600))
    df = _df_from_closes(closes)
    res = run_trend_research(df, "EUR_USD", TrendParams(ma_n=50), walk_forward_pct=0.3)
    assert "full" in res and "walk_forward" in res
    if res["full"]["trades"] >= 3:
        assert res["full"]["top3_pct_of_net"] is not None


def test_not_enough_bars_is_handled():
    df = _df_from_closes(list(1.0 + np.linspace(0, 0.1, 30)))
    res = simulate_trend(df, "EUR_USD", TrendParams())
    assert res["trades"] == 0
