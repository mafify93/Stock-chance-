"""Combines the rule-based signal, ML prediction, and optional LLM analysis
into a single action + confidence.

Used by both `/api/ai/analysis` and the auto-trader, so the recommendation
shown to the user and the one the auto-trader acts on are always identical.
"""
from __future__ import annotations


def _direction(action: str) -> int:
    action = action.upper()
    if action in ("BUY", "STRONG_BUY", "DAY_BUY"):
        return 1
    if action in ("SELL", "STRONG_SELL", "DAY_SELL"):
        return -1
    return 0


def combine(
    signal: dict,
    ml: dict | None,
    llm: dict | None,
    insider: dict | None = None,
    sentiment: dict | None = None,
) -> tuple[str, float]:
    """Returns `(combined_action, combined_confidence)`.

    `combined_action` is "BUY" | "SELL" | "HOLD". `combined_confidence` is
    0..100. The three primary sources (rule-based signal, ML model, LLM
    analyst) each contribute an equally-weighted vote in [-1, 1] (direction *
    confidence) at full weight 1.0.

    Two optional auxiliary factors - `insider` (SEC Form 4 insider trading)
    and `sentiment` (earnings sentiment) - contribute at a lower weight of 0.5
    each, so they can nudge a borderline decision without overriding the
    primary sources. Any source that isn't available (no trained ML model, no
    LLM configured, no insider activity, sentiment disabled) is simply excluded
    rather than counted as neutral.
    """
    weighted_sum = _direction(signal["action"]) * (signal["confidence"] / 100)
    total_weight = 1.0

    if ml is not None:
        weighted_sum += _direction(ml["action"]) * (ml["confidence"] / 100)
        total_weight += 1.0

    if llm is not None:
        weighted_sum += _direction(llm["action"]) * (llm["confidence"] / 100)
        total_weight += 1.0

    # Auxiliary factors carry half the weight of a primary source.
    if insider is not None:
        weighted_sum += _direction(insider["action"]) * (insider["confidence"] / 100) * 0.5
        total_weight += 0.5

    if sentiment is not None:
        weighted_sum += _direction(sentiment["action"]) * (sentiment["confidence"] / 100) * 0.5
        total_weight += 0.5

    score = weighted_sum / total_weight
    confidence = round(min(100.0, abs(score) * 100), 1)

    if score >= 0.2:
        action = "BUY"
    elif score <= -0.2:
        action = "SELL"
    else:
        action = "HOLD"

    return action, confidence
