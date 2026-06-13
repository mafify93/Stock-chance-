from app.intraday import DaySignalResult
from app.signals import SignalResult
from app.top_pick import evaluate_opportunity


def _daily(score, reasons=None, levels=None):
    return SignalResult(
        symbol="TEST",
        action="BUY" if score > 0 else "SELL",
        score=score,
        confidence=min(100.0, abs(score) * 100 + 5),
        price=100.0,
        reasons=reasons or ["Price is above its 50-day average - uptrend"],
        indicators={},
        levels=levels or {},
    )


def _day(score, entry=None, target=None, stop=None, reasons=None):
    return DaySignalResult(
        symbol="TEST",
        action="DAY_BUY" if score > 0 else "DAY_SELL",
        score=score,
        confidence=min(100.0, abs(score) * 100 + 10),
        price=101.0,
        vwap=100.5,
        session_open=99.0,
        session_high=102.0,
        session_low=98.5,
        change_from_open_pct=2.0,
        reasons=reasons or ["Price is above today's VWAP - buyers in control"],
        entry=entry,
        target=target,
        stop=stop,
        suspected_profit_pct=1.5 if score > 0 else None,
        suspected_profit_amount=1.5 if score > 0 else None,
    )


def test_strong_bullish_alignment_yields_strong_buy():
    daily = _daily(0.6)
    day = _day(0.7, entry=101.0, target=103.0, stop=99.5)
    analyst = {"target_mean_price": 115.0, "number_of_analyst_opinions": 20}

    opp = evaluate_opportunity("TEST", daily, day, analyst, change_percent=2.0)

    assert opp.action == "STRONG_BUY"
    assert opp.headline == "Buy TEST Now"
    assert opp.opportunity_score > 0.5
    assert opp.entry == 101.0
    assert opp.target == 103.0
    assert opp.stop == 99.5
    assert opp.analyst_target_upside_pct is not None
    assert opp.analyst_target_upside_pct > 0
    assert any("analyst" in r.lower() for r in opp.reasons)


def test_strong_bearish_alignment_yields_avoid():
    daily = _daily(-0.6, reasons=["Price is below its 200-day average - downtrend"])
    day = _day(-0.7, reasons=["Price is below today's VWAP - sellers in control"])
    analyst = {"target_mean_price": 85.0, "number_of_analyst_opinions": 10}

    opp = evaluate_opportunity("TEST", daily, day, analyst, change_percent=-2.0)

    assert opp.action == "STRONG_SELL"
    assert opp.headline == "Avoid TEST Right Now"
    assert opp.opportunity_score < -0.5


def test_no_intraday_data_falls_back_to_daily_and_analyst():
    daily = _daily(0.4, levels={"suggested_entry": 100.0, "stop_loss": 97.0, "take_profit": 106.0})
    opp = evaluate_opportunity("TEST", daily, None, analyst=None, change_percent=1.0)

    assert opp.price == daily.price
    assert opp.entry == 100.0
    assert opp.target == 106.0
    assert opp.stop == 97.0
    assert opp.analyst_target_upside_pct is None


def test_mixed_signals_yield_hold():
    daily = _daily(0.05)
    day = _day(-0.05)
    opp = evaluate_opportunity("TEST", daily, day, analyst=None)

    assert opp.action == "HOLD"
    assert opp.headline == "TEST: Hold Steady"
