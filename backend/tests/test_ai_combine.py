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


def test_combine_none_aux_reproduces_three_arg():
    signal = _signal("STRONG_BUY", 90)
    ml = {"action": "BUY", "confidence": 80}
    llm = {"action": "BUY", "confidence": 70}
    base = combine(signal, ml, llm)
    with_none_aux = combine(signal, ml, llm, None, None)
    assert with_none_aux == base


def test_combine_insider_nudges_borderline_hold_to_buy():
    # Signal alone is borderline HOLD: score 0.18 < 0.2 threshold.
    signal = _signal("BUY", 18)
    hold_action, _ = combine(signal, None, None)
    assert hold_action == "HOLD"

    # A strong insider BUY adds positive weight, pushing the average over 0.2.
    insider = {"action": "BUY", "confidence": 100}
    action, _ = combine(signal, None, None, insider=insider)
    assert action == "BUY"


def test_combine_auxiliary_weight_is_half():
    # signal BUY@100 -> +1.0 at weight 1.0.
    # insider SELL@100 -> -1.0 at weight 0.5.
    # score = (1.0 - 0.5) / (1.0 + 0.5) = 0.5/1.5 = 0.3333 -> BUY, conf 33.3.
    signal = _signal("BUY", 100)
    insider = {"action": "SELL", "confidence": 100}
    action, confidence = combine(signal, None, None, insider=insider)
    assert action == "BUY"
    assert confidence == 33.3

    # Same magnitudes but if the aux were full weight it would average to 0.0
    # (HOLD). The BUY result above proves the aux carries less than full weight.
    # Sentiment uses the identical 0.5 weighting.
    sentiment = {"action": "SELL", "confidence": 100}
    action_s, confidence_s = combine(signal, None, None, sentiment=sentiment)
    assert action_s == "BUY"
    assert confidence_s == 33.3
