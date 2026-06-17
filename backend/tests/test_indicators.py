import numpy as np
import pandas as pd

from app.indicators import (
    average_true_range,
    bollinger_bands,
    compute_all_indicators,
    ema,
    macd,
    rsi,
    sma,
    stochastic_oscillator,
)


def _make_df(n=300, seed=42):
    rng = np.random.default_rng(seed)
    base = 100 + np.cumsum(rng.normal(0, 1, n))
    high = base + rng.uniform(0, 1, n)
    low = base - rng.uniform(0, 1, n)
    close = base
    open_ = base + rng.normal(0, 0.5, n)
    volume = rng.uniform(1e6, 5e6, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}, index=idx)


def test_sma_basic():
    s = pd.Series([1, 2, 3, 4, 5])
    result = sma(s, 3)
    assert np.isnan(result.iloc[1])
    assert result.iloc[2] == 2
    assert result.iloc[4] == 4


def test_ema_converges_for_constant_series():
    s = pd.Series([10.0] * 50)
    result = ema(s, 12)
    assert abs(result.iloc[-1] - 10.0) < 1e-6


def test_rsi_bounds():
    df = _make_df()
    r = rsi(df["Close"])
    valid = r.dropna()
    assert (valid >= 0).all()
    assert (valid <= 100).all()


def test_rsi_extremes_for_monotonic_series():
    up = pd.Series(np.arange(1, 50, dtype=float))
    down = pd.Series(np.arange(50, 1, -1, dtype=float))
    assert rsi(up).iloc[-1] > 90
    assert rsi(down).iloc[-1] < 10


def test_macd_shape():
    df = _make_df()
    result = macd(df["Close"])
    assert set(result.keys()) == {"macd", "signal", "hist"}
    for series in result.values():
        assert len(series) == len(df)


def test_bollinger_bands_ordering():
    df = _make_df()
    bb = bollinger_bands(df["Close"])
    valid = bb["mid"].dropna().index
    assert (bb["upper"][valid] >= bb["mid"][valid]).all()
    assert (bb["lower"][valid] <= bb["mid"][valid]).all()


def test_stochastic_bounds():
    df = _make_df()
    stoch = stochastic_oscillator(df)
    valid_k = stoch["k"].dropna()
    assert (valid_k >= -1e-9).all()
    assert (valid_k <= 100 + 1e-9).all()


def test_atr_non_negative():
    df = _make_df()
    atr = average_true_range(df)
    assert (atr.dropna() >= 0).all()


def test_compute_all_indicators_has_expected_columns():
    df = _make_df()
    out = compute_all_indicators(df)
    expected = {
        "sma_20", "sma_50", "sma_200", "ema_12", "ema_26", "rsi_14",
        "macd", "macd_signal", "macd_hist", "bb_mid", "bb_upper", "bb_lower",
        "stoch_k", "stoch_d", "atr_14", "adx_14", "volume_sma_20",
    }
    assert expected.issubset(out.columns)
    # last row should be fully computed given 300 days of history
    assert not out.iloc[-1][list(expected)].isna().any()
