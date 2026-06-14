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


def combine(signal: dict, ml: dict | None, llm: dict | None) -> tuple[str, float]:
    """Returns `(combined_action, combined_confidence)`.

    `combined_action` is "BUY" | "SELL" | "HOLD". `combined_confidence` is
    0..100. Each available source (rule-based signal, ML model, LLM analyst)
    contributes an equally-weighted vote in [-1, 1] (direction * confidence);
    sources that aren't available (no trained ML model, no LLM configured)
    are simply excluded rather than counted as neutral.
    """
    weighted_sum = _direction(signal["action"]) * (signal["confidence"] / 100)
    total_weight = 1.0

    if ml is not None:
        weighted_sum += _direction(ml["action"]) * (ml["confidence"] / 100)
        total_weight += 1.0

    if llm is not None:
        weighted_sum += _direction(llm["action"]) * (llm["confidence"] / 100)
        total_weight += 1.0

    score = weighted_sum / total_weight
    confidence = round(min(100.0, abs(score) * 100), 1)

    if score >= 0.2:
        action = "BUY"
    elif score <= -0.2:
        action = "SELL"
    else:
        action = "HOLD"

    return action, confidence
