from app.intraday import compute_day_signal


def test_rising_intraday_is_day_buy(intraday_m5):
    result = compute_day_signal("EUR_USD", intraday_m5)
    assert result.action == "DAY_BUY"
    assert result.target_pips is not None and result.target_pips > 0
    assert result.stop_pips is not None and result.stop_pips > 0
    assert result.change_from_open_pips > 0


def test_change_reported_in_pips(intraday_m5):
    result = compute_day_signal("EUR_USD", intraday_m5)
    # Fixture runs 00:00–09:55 UTC and climbs 40 pips total, but compute_day_signal
    # now anchors to London open (07:00 UTC). Only the 07:00–09:55 portion counts
    # (~35 of 120 bars), giving roughly 12 pips from the London-open session reference.
    assert 8 < result.change_from_open_pips < 20
