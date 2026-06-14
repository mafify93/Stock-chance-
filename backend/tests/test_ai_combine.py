from app.ai_combine import combine


def _signal(action="HOLD", confidence=50.0):
    return {"action": action, "score": 0.0, "confidence": confidence, "price": 100.0, "reasons": []}


def test_combine_signal_only_buy():
    action, confidence = combine(_signal("BUY", 80), None, None)
    assert action == "BUY"
    assert confidence == 80.0


def test_combine_signal_only_hold_stays_hold():
    action, confidence = combine(_signal("HOLD", 10), None, None)
    assert action == "HOLD"


def test_combine_all_sources_agree_buy():
    signal = _signal("STRONG_BUY", 90)
    ml = {"action": "BUY", "score": 0.4, "confidence": 80, "horizon_days": 5, "model_version": None, "probability_up": 0.7}
    llm = {"action": "BUY", "confidence": 70, "summary": "looks good", "model": "test"}
    action, confidence = combine(signal, ml, llm)
    assert action == "BUY"
    assert confidence > 50


def test_combine_conflicting_sources_can_average_to_hold():
    signal = _signal("BUY", 100)
    ml = {"action": "SELL", "score": -1.0, "confidence": 100, "horizon_days": 5, "model_version": None, "probability_up": 0.0}
    action, confidence = combine(signal, ml, None)
    assert action == "HOLD"


def test_combine_sell_dominant():
    signal = _signal("STRONG_SELL", 90)
    action, confidence = combine(signal, None, None)
    assert action == "SELL"
    assert confidence == 90.0
