""""Top Pick" recommendation engine.

Combines three independent signals into one ranked, plain-language "what to
buy right now" idea per symbol:

- the longer-term daily trend (`app/signals.py`)
- today's intraday momentum (`app/intraday.py`)
- Wall Street analyst price targets (free, bundled with Yahoo Finance)

This is still rule-based technical analysis - not a prediction - but
combining all three viewpoints into a single score lets the app surface one
clear "best idea right now" instead of a dozen raw indicators.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .intraday import DaySignalResult
from .signals import SignalResult


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


@dataclass
class Opportunity:
    symbol: str
    action: str  # "STRONG_BUY" | "BUY" | "HOLD" | "SELL" | "STRONG_SELL"
    headline: str
    summary: str
    opportunity_score: float  # -1.0 .. +1.0
    confidence: float  # 0..100
    price: float
    change_percent: float | None = None
    entry: float | None = None
    target: float | None = None
    stop: float | None = None
    suspected_profit_pct: float | None = None
    suspected_profit_amount: float | None = None
    analyst_target_upside_pct: float | None = None
    reasons: list[str] = field(default_factory=list)


_HEADLINES = {
    "STRONG_BUY": "Buy {symbol} Now",
    "BUY": "{symbol} Looks Like a Buy",
    "HOLD": "{symbol}: Hold Steady",
    "SELL": "{symbol} Looks Weak",
    "STRONG_SELL": "Avoid {symbol} Right Now",
}

_SUMMARIES = {
    "STRONG_BUY": (
        "Today's momentum and the longer-term trend are both pointing up{analyst_clause} - "
        "this is one of the strongest setups available right now."
    ),
    "BUY": (
        "The signs lean positive{analyst_clause}, but the case isn't overwhelming - "
        "a smaller, cautious position makes more sense than going all-in."
    ),
    "HOLD": (
        "Signals are mixed right now{analyst_clause} - probably best to wait for a "
        "clearer setup before putting money in."
    ),
    "SELL": (
        "Momentum is fading{analyst_clause} - if you're already holding this one, it "
        "may be a good time to take profits or cut losses."
    ),
    "STRONG_SELL": (
        "Both today's action and the broader trend are pointing down{analyst_clause} - "
        "best to steer clear for now."
    ),
}


def _score_to_action(score: float) -> str:
    if score >= 0.5:
        return "STRONG_BUY"
    if score >= 0.15:
        return "BUY"
    if score <= -0.5:
        return "STRONG_SELL"
    if score <= -0.15:
        return "SELL"
    return "HOLD"


def evaluate_opportunity(
    symbol: str,
    daily: SignalResult,
    day: DaySignalResult | None,
    analyst: dict | None,
    change_percent: float | None = None,
) -> Opportunity:
    """Combine the daily trend, today's intraday signal, and analyst targets.

    `day` may be `None` when intraday data isn't available (e.g. market
    closed for a while with no recent bars) - the daily trend and analyst
    targets are still enough to form an opinion.
    """
    price = day.price if day is not None else daily.price

    votes: list[tuple[float, float]] = [(daily.score, 1.0)]
    if day is not None:
        votes.append((day.score, 1.4))

    analyst_upside_pct: float | None = None
    if analyst:
        target_mean = analyst.get("target_mean_price")
        if target_mean and price:
            analyst_upside_pct = round((target_mean - price) / price * 100, 2)
            votes.append((_clip(analyst_upside_pct / 10), 0.8))

    weighted_sum = sum(_clip(v) * w for v, w in votes)
    total_weight = sum(w for _, w in votes)
    opportunity_score = _clip(weighted_sum / total_weight) if total_weight else 0.0

    action = _score_to_action(opportunity_score)
    confidence = round(min(100.0, abs(opportunity_score) * 100 + 5), 1)

    analyst_clause = ""
    if analyst_upside_pct is not None:
        if analyst_upside_pct > 0:
            analyst_clause = f", and Wall Street analysts see about {analyst_upside_pct:.1f}% upside from here"
        else:
            analyst_clause = f", though Wall Street's average price target is about {abs(analyst_upside_pct):.1f}% below the current price"

    headline = _HEADLINES[action].format(symbol=symbol)
    summary = _SUMMARIES[action].format(analyst_clause=analyst_clause)

    reasons: list[str] = []
    if day is not None:
        reasons.extend(day.reasons[:2])
    reasons.extend(daily.reasons[:2])
    if analyst_upside_pct is not None and analyst and analyst.get("number_of_analyst_opinions"):
        direction = "above" if analyst_upside_pct > 0 else "below"
        reasons.append(
            f"Average analyst price target is {abs(analyst_upside_pct):.1f}% {direction} the current "
            f"price (based on {analyst['number_of_analyst_opinions']} analysts)"
        )

    entry = target = stop = None
    suspected_profit_pct = suspected_profit_amount = None
    if day is not None and day.entry is not None:
        entry, target, stop = day.entry, day.target, day.stop
        suspected_profit_pct = day.suspected_profit_pct
        suspected_profit_amount = day.suspected_profit_amount
    elif daily.levels:
        entry = daily.levels.get("suggested_entry") or daily.levels.get("suggested_exit")
        target = daily.levels.get("take_profit") or daily.levels.get("take_profit_short")
        stop = daily.levels.get("stop_loss") or daily.levels.get("stop_loss_short")

    return Opportunity(
        symbol=symbol,
        action=action,
        headline=headline,
        summary=summary,
        opportunity_score=round(opportunity_score, 4),
        confidence=confidence,
        price=round(price, 2),
        change_percent=round(change_percent, 2) if change_percent is not None else None,
        entry=entry,
        target=target,
        stop=stop,
        suspected_profit_pct=suspected_profit_pct,
        suspected_profit_amount=suspected_profit_amount,
        analyst_target_upside_pct=analyst_upside_pct,
        reasons=reasons,
    )
