"""Combine the swing (higher-timeframe) signal and the intraday signal into a
single ranked "what should I trade right now" idea per currency pair.

This is the engine behind the Today tab's Top Pick and the morning scan. It
weighs the longer-term trend more heavily for direction but lets a strong,
agreeing intraday signal boost conviction (and flags disagreement, which is
usually a reason to stand aside).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import pips
from .intraday import DaySignalResult
from .signals import SignalResult


@dataclass
class Opportunity:
    pair: str
    action: str  # "STRONG_BUY" | "BUY" | "HOLD" | "SELL" | "STRONG_SELL"
    headline: str
    summary: str
    opportunity_score: float
    confidence: float
    price: float
    change_from_open_pips: float | None = None
    entry: float | None = None
    target: float | None = None
    stop: float | None = None
    target_pips: float | None = None
    stop_pips: float | None = None
    reasons: list[str] = field(default_factory=list)


def _action_word(action: str) -> str:
    return {
        "STRONG_BUY": "Strong Buy",
        "BUY": "Buy",
        "HOLD": "Hold",
        "SELL": "Sell",
        "STRONG_SELL": "Strong Sell",
    }.get(action, action.title())


def evaluate_opportunity(
    pair: str,
    swing: SignalResult,
    day: DaySignalResult | None,
) -> Opportunity:
    """Blend a swing signal and (optional) intraday signal into one idea."""
    display = pips.display(pair)

    # Direction comes mostly from the swing trend; the intraday signal adjusts
    # conviction up (agreement) or down (disagreement).
    swing_score = swing.score
    day_score = day.score if day is not None else 0.0

    aligned = (swing_score > 0 and day_score > 0) or (swing_score < 0 and day_score < 0)
    conflict = (swing_score > 0 and day_score < 0) or (swing_score < 0 and day_score > 0)

    combined = swing_score * 0.65 + day_score * 0.35
    if day is None:
        combined = swing_score

    if combined >= 0.5:
        action = "STRONG_BUY"
    elif combined >= 0.15:
        action = "BUY"
    elif combined <= -0.5:
        action = "STRONG_SELL"
    elif combined <= -0.15:
        action = "SELL"
    else:
        action = "HOLD"

    confidence = round(min(100.0, abs(combined) * 100 + 5), 1)
    opportunity_score = round(abs(combined) * (1.15 if aligned else 1.0), 4)

    reasons = list(swing.reasons[:3])
    if day is not None:
        reasons.extend(day.reasons[:2])

    if conflict:
        headline = f"{display}: mixed signals"
        summary = (
            f"The higher-timeframe trend and today's intraday momentum disagree on "
            f"{display}. Often a reason to wait for them to line up before risking capital."
        )
    elif action in ("STRONG_BUY", "BUY"):
        headline = f"{display}: {_action_word(action).lower()} setup"
        summary = (
            f"{display} is trending up{' and intraday momentum agrees' if aligned else ''}. "
            f"{'A high-conviction long.' if action == 'STRONG_BUY' else 'A long bias for now.'}"
        )
    elif action in ("STRONG_SELL", "SELL"):
        headline = f"{display}: {_action_word(action).lower()} setup"
        summary = (
            f"{display} is trending down{' and intraday momentum agrees' if aligned else ''}. "
            f"{'A high-conviction short.' if action == 'STRONG_SELL' else 'A short bias for now.'}"
        )
    else:
        headline = f"{display}: no clear edge"
        summary = f"{display} is range-bound with no clear directional edge right now."

    # Prefer the intraday entry/stop/target when we have a same-day signal in
    # the trade direction; otherwise fall back to the swing levels.
    entry = target = stop = target_pips = stop_pips = None
    if day is not None and day.action in ("DAY_BUY", "DAY_SELL") and not conflict:
        entry, target, stop = day.entry, day.target, day.stop
        target_pips, stop_pips = day.target_pips, day.stop_pips
    elif swing.levels:
        entry = swing.levels.get("suggested_entry")
        target = swing.levels.get("take_profit")
        stop = swing.levels.get("stop_loss")
        target_pips = swing.levels.get("target_pips")
        stop_pips = swing.levels.get("stop_pips")

    return Opportunity(
        pair=pair,
        action=action,
        headline=headline,
        summary=summary,
        opportunity_score=opportunity_score,
        confidence=confidence,
        price=swing.price,
        change_from_open_pips=day.change_from_open_pips if day is not None else None,
        entry=entry,
        target=target,
        stop=stop,
        target_pips=target_pips,
        stop_pips=stop_pips,
        reasons=reasons,
    )
