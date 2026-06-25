import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def uptrend_h1() -> pd.DataFrame:
    """A clean rising H1 series with enough bars for SMA-200."""
    n = 300
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    base = 1.0500 + np.linspace(0, 0.0300, n)  # steady climb, EUR/USD-like
    noise = np.sin(np.linspace(0, 30, n)) * 0.0005
    close = base + noise
    df = pd.DataFrame(
        {
            "Open": close - 0.0002,
            "High": close + 0.0006,
            "Low": close - 0.0006,
            "Close": close,
            "Volume": np.full(n, 1200.0),
        },
        index=idx,
    )
    return df


@pytest.fixture
def intraday_m5() -> pd.DataFrame:
    """A single UTC day of rising 5-minute bars."""
    n = 120
    idx = pd.date_range("2024-03-01 00:00", periods=n, freq="5min", tz="UTC")
    close = 1.1000 + np.linspace(0, 0.0040, n)
    df = pd.DataFrame(
        {
            "Open": close - 0.0001,
            "High": close + 0.0003,
            "Low": close - 0.0003,
            "Close": close,
            "Volume": np.full(n, 800.0),
        },
        index=idx,
    )
    return df
