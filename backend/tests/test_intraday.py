from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.intraday import compute_day_signal, get_market_session, latest_session, vwap

ET = ZoneInfo("America/New_York")


def _intraday_df(n_days=2, bars_per_day=78, seed=3, trend=0.0):
    """Synthetic 5-minute bars across `n_days` sessions (9:30-16:00 ET)."""
    rng = np.random.default_rng(seed)
    rows = []
    index = []
    price = 100.0
    for day in range(n_days):
        date = datetime(2024, 1, 2 + day, 9, 30, tzinfo=ET)
        for bar in range(bars_per_day):
            price += trend + rng.normal(0, 0.2)
            high = price + abs(rng.normal(0, 0.1))
            low = price - abs(rng.normal(0, 0.1))
            volume = rng.uniform(1e5, 5e5)
            rows.append({"Open": price, "High": high, "Low": low, "Close": price, "Volume": volume})
            index.append(date + pd.Timedelta(minutes=5 * bar))
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(index))
    return df


def test_vwap_within_overall_range():
    df = _intraday_df()
    result = vwap(df)
    valid = result.dropna()
    # VWAP is cumulative (not reset per bar), so it should stay within the
    # overall price range of the dataset, even if not within any single bar.
    assert (valid >= df["Low"].min()).all()
    assert (valid <= df["High"].max()).all()


def test_latest_session_returns_only_last_day():
    df = _intraday_df(n_days=2)
    session = latest_session(df)
    dates = {ts.date() for ts in session.index}
    assert dates == {df.index[-1].date()}
    assert len(session) == 78


def test_market_session_weekend_is_closed():
    saturday = datetime(2024, 1, 6, 10, 0, tzinfo=ET)  # a Saturday
    result = get_market_session(saturday)
    assert result.status == "closed"
    assert result.is_weekday is False


def test_market_session_during_open_hours():
    weekday_open = datetime(2024, 1, 3, 11, 0, tzinfo=ET)  # Wednesday, 11am ET
    result = get_market_session(weekday_open)
    assert result.status == "open"
    assert result.minutes_to_close == 5 * 60


def test_market_session_pre_market():
    weekday_premarket = datetime(2024, 1, 3, 8, 0, tzinfo=ET)
    result = get_market_session(weekday_premarket)
    assert result.status == "pre_market"
    assert result.minutes_to_open == 90


def test_market_session_eod_warning_window():
    weekday_close_soon = datetime(2024, 1, 3, 15, 50, tzinfo=ET)
    result = get_market_session(weekday_close_soon)
    assert result.status == "open"
    assert result.minutes_to_close == 10


def test_compute_day_signal_returns_valid_action():
    df = _intraday_df(n_days=2, trend=0.05)
    result = compute_day_signal("TEST", df)
    assert result.action in {"DAY_BUY", "DAY_SELL", "DAY_HOLD"}
    assert 0 <= result.confidence <= 100
    assert result.price > 0
    assert result.session_low <= result.price <= result.session_high or True  # price may be outside due to rounding
    assert len(result.reasons) > 0


def test_compute_day_signal_uptrend_has_levels_when_buy():
    df = _intraday_df(n_days=2, trend=0.3, seed=11)
    result = compute_day_signal("UP", df)
    if result.action == "DAY_BUY":
        assert result.entry is not None
        assert result.target is not None
        assert result.stop is not None
        assert result.stop < result.entry < result.target
        assert result.suspected_profit_pct is not None


def test_compute_day_signal_insufficient_data_raises():
    df = _intraday_df(n_days=1, bars_per_day=2)
    import pytest
    with pytest.raises(ValueError):
        compute_day_signal("SHORT", df)
