from datetime import datetime, timezone

from app.sessions import (
    get_market_session,
    in_blackout,
    is_rollover,
    ny_close_imminent,
)


def _utc(y, m, d, h, mn=0):
    return datetime(y, m, d, h, mn, tzinfo=timezone.utc)


# ── get_market_session: basic weekend / session detection ────────────────────

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
    # March 1 2024 is a Friday; US still on EST (UTC-5). 22:00 UTC = 17:00 EST → closed.
    s = get_market_session(_utc(2024, 3, 1, 22))
    assert s.status == "closed"


# ── DST-aware Friday close ───────────────────────────────────────────────────

def test_friday_21utc_winter_is_open():
    # January 19 2024 is a Friday; US on EST (UTC-5). 21:00 UTC = 16:00 EST → still open.
    s = get_market_session(_utc(2024, 1, 19, 21))
    assert s.status == "open"


def test_friday_22utc_winter_is_closed():
    # January 19 2024, 22:00 UTC = 17:00 EST → NY closed, market closed.
    s = get_market_session(_utc(2024, 1, 19, 22))
    assert s.status == "closed"


def test_friday_21utc_summer_is_closed():
    # June 21 2024 is a Friday; US on EDT (UTC-4). 21:00 UTC = 17:00 EDT → closed.
    s = get_market_session(_utc(2024, 6, 21, 21))
    assert s.status == "closed"


def test_friday_20utc_summer_is_open():
    # June 21 2024, 20:00 UTC = 16:00 EDT → NY still open.
    s = get_market_session(_utc(2024, 6, 21, 20))
    assert s.status == "open"


# ── DST-aware London session ─────────────────────────────────────────────────

def test_london_open_in_bst():
    # June 10 2024 (Monday); UK on BST (UTC+1). 07:00 UTC = 08:00 BST → London open.
    s = get_market_session(_utc(2024, 6, 10, 7))
    assert "London" in s.active_sessions


def test_london_closed_at_7utc_in_winter():
    # January 15 2024 (Monday); UK on GMT (UTC+0). 07:00 UTC = 07:00 GMT → before open.
    s = get_market_session(_utc(2024, 1, 15, 7))
    assert "London" not in s.active_sessions


# ── is_rollover ──────────────────────────────────────────────────────────────

def test_rollover_active_at_ny_4_55pm_summer():
    # June 10 2024; EDT (UTC-4). 20:55 UTC = 16:55 ET → rollover window.
    assert is_rollover(_utc(2024, 6, 10, 20, 55)) is True


def test_rollover_active_at_ny_5_05pm_summer():
    # 21:05 UTC = 17:05 ET → still in rollover window.
    assert is_rollover(_utc(2024, 6, 10, 21, 5)) is True


def test_rollover_inactive_at_ny_5_11pm():
    # 21:11 UTC = 17:11 ET → outside the 10-minute rollover window.
    assert is_rollover(_utc(2024, 6, 10, 21, 11)) is False


def test_rollover_inactive_midday():
    # 16:00 UTC = 12:00 ET (summer) → not near rollover.
    assert is_rollover(_utc(2024, 6, 10, 16, 0)) is False


def test_rollover_dst_winter():
    # January 15 2024; EST (UTC-5). 21:55 UTC = 16:55 ET → rollover.
    assert is_rollover(_utc(2024, 1, 15, 21, 55)) is True
    # 22:05 UTC = 17:05 ET → still rollover.
    assert is_rollover(_utc(2024, 1, 15, 22, 5)) is True
    # 22:11 UTC = 17:11 ET → outside window.
    assert is_rollover(_utc(2024, 1, 15, 22, 11)) is False


# ── ny_close_imminent ────────────────────────────────────────────────────────

def test_ny_close_imminent_2min_before_summer():
    # 20:58 UTC = 16:58 EDT → 2 minutes from 17:00 close → imminent.
    assert ny_close_imminent(_utc(2024, 6, 10, 20, 58)) is True


def test_ny_close_imminent_exactly_at_close():
    # 21:00 UTC = 17:00 EDT → 0 minutes remaining → imminent.
    assert ny_close_imminent(_utc(2024, 6, 10, 21, 0)) is True


def test_ny_close_not_imminent_6min_before():
    # 20:54 UTC = 16:54 EDT → 6 minutes away → not imminent (default within_min=5).
    assert ny_close_imminent(_utc(2024, 6, 10, 20, 54)) is False


def test_ny_close_not_imminent_after_close():
    # 21:01 UTC = 17:01 EDT → already past close → not imminent.
    assert ny_close_imminent(_utc(2024, 6, 10, 21, 1)) is False


def test_ny_close_imminent_dst_winter():
    # January 15 2024; EST (UTC-5). Close is at 22:00 UTC.
    assert ny_close_imminent(_utc(2024, 1, 15, 21, 58)) is True   # 2 min before
    assert ny_close_imminent(_utc(2024, 1, 15, 21, 54)) is False  # 6 min before
    assert ny_close_imminent(_utc(2024, 1, 15, 22, 1)) is False   # 1 min after


def test_ny_close_imminent_custom_window():
    # 21:53 UTC = 16:53 EDT → 7 min before; default window misses it, 10-min window catches it.
    assert ny_close_imminent(_utc(2024, 6, 10, 20, 53), within_min=5) is False
    assert ny_close_imminent(_utc(2024, 6, 10, 20, 53), within_min=10) is True


# ── in_blackout ──────────────────────────────────────────────────────────────

def test_in_blackout_matches_window():
    # 13:30 UTC falls inside the 13:25-13:35 window.
    assert in_blackout(_utc(2024, 6, 10, 13, 30), ["13:25-13:35"]) is True


def test_in_blackout_outside_window():
    # 13:40 UTC is after the window ends.
    assert in_blackout(_utc(2024, 6, 10, 13, 40), ["13:25-13:35"]) is False


def test_in_blackout_empty_list():
    assert in_blackout(_utc(2024, 6, 10, 13, 30), []) is False


def test_in_blackout_multiple_windows():
    windows = ["08:25-08:35", "12:55-13:05", "14:55-15:05"]
    assert in_blackout(_utc(2024, 6, 10, 13, 0), windows) is True   # NFP window
    assert in_blackout(_utc(2024, 6, 10, 10, 0), windows) is False  # quiet period
    assert in_blackout(_utc(2024, 6, 10, 8, 25), windows) is True   # start of first window


def test_in_blackout_malformed_entry_ignored():
    # A malformed entry must not crash the scan.
    assert in_blackout(_utc(2024, 6, 10, 13, 30), ["bad-entry", "13:25-13:35"]) is True
    assert in_blackout(_utc(2024, 6, 10, 13, 30), ["oops"]) is False
