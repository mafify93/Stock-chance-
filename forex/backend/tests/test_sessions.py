from datetime import datetime, timezone

from app.sessions import get_market_session


def _utc(y, m, d, h):
    return datetime(y, m, d, h, 0, tzinfo=timezone.utc)


def test_saturday_is_closed():
    s = get_market_session(_utc(2024, 3, 2, 12))  # Saturday
    assert s.status == "closed"
    assert s.minutes_to_open is not None


def test_sunday_before_open_is_closed():
    s = get_market_session(_utc(2024, 3, 3, 10))  # Sunday 10:00 UTC, before 22:00
    assert s.status == "closed"


def test_sunday_after_open_is_open():
    s = get_market_session(_utc(2024, 3, 3, 23))  # Sunday 23:00 UTC
    assert s.status == "open"
    assert "Sydney" in s.active_sessions


def test_london_newyork_overlap_is_high_liquidity():
    s = get_market_session(_utc(2024, 3, 5, 14))  # Tuesday 14:00 UTC
    assert s.status == "open"
    assert s.is_high_liquidity is True
    assert "London" in s.active_sessions
    assert "New York" in s.active_sessions


def test_friday_after_close_is_closed():
    s = get_market_session(_utc(2024, 3, 1, 22))  # Friday 22:00 UTC, after 21:00
    assert s.status == "closed"
