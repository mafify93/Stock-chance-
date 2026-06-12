"""Pre-market "what to buy at the open" scan.

Combines the longer-term daily trend (from `app/signals.py`) with the
overnight/pre-market price move to surface a short list of candidates that
look attractive for a same-day (buy-at-open, sell-before-close) trade, with
a rough "suspected profit" target derived from each stock's typical daily
volatility (ATR).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .signals import analyze


@dataclass
class MorningCandidate:
    symbol: str
    action: str  # "BUY_AT_OPEN" | "WATCH_DIP" | "AVOID" | "NEUTRAL"
    price: float
    gap_percent: float | None
    data_mode: str
    daily_trend: str
    daily_score: float
    suspected_profit_pct: float
    suspected_profit_amount: float
    plan: str
    reasons: list[str] = field(default_factory=list)
    rank_score: float = 0.0


def evaluate_candidate(symbol: str, daily_df: pd.DataFrame, premarket: dict) -> MorningCandidate:
    daily = analyze(symbol, daily_df)

    price = premarket.get("price") or daily.price
    gap_pct = premarket.get("change_percent")
    mode = premarket.get("mode", "last_close")

    atr = daily.indicators.get("atr_14") or 0.0
    suspected_profit_pct = round(atr / price * 100, 2) if price else 0.0
    suspected_profit_amount = round(atr, 2)

    bullish_trend = daily.score > 0.15
    bearish_trend = daily.score < -0.15

    reasons: list[str] = []
    action = "NEUTRAL"
    plan = "No clear edge today based on the data available - consider sitting this one out."
    rank_score = 0.0

    if gap_pct is not None:
        if gap_pct > 0.3 and bullish_trend:
            action = "BUY_AT_OPEN"
            reasons.append(f"Trading {gap_pct:+.2f}% vs. yesterday's close, and already in an uptrend on the daily chart")
            plan = (
                f"Consider buying near the open if the price holds above ${price:.2f}. "
                f"A reasonable target is roughly +{suspected_profit_pct:.1f}% "
                f"(about ${suspected_profit_amount:.2f}) - and plan to sell by the end of the day either way."
            )
            rank_score = abs(gap_pct) + daily.score * 2
        elif gap_pct < -0.3 and bearish_trend:
            action = "AVOID"
            reasons.append(f"Trading {gap_pct:+.2f}% vs. yesterday's close, and already in a downtrend on the daily chart")
            plan = "Downward momentum heading into the open makes this risky for a same-day buy - best to wait and watch."
            rank_score = abs(gap_pct) + abs(daily.score)
        elif abs(gap_pct) < 0.3 and bullish_trend:
            action = "WATCH_DIP"
            reasons.append("Roughly flat overnight, but in a longer-term uptrend")
            plan = (
                f"Watch the first 15-30 minutes - if it dips slightly and then turns back up, that's often a "
                f"good entry. Target roughly +{suspected_profit_pct:.1f}% (about ${suspected_profit_amount:.2f}), "
                f"and sell by end of day."
            )
            rank_score = daily.score * 1.5
        elif gap_pct < -0.3 and bullish_trend:
            action = "WATCH_DIP"
            reasons.append(f"Down {gap_pct:+.2f}% overnight despite a longer-term uptrend - could be a buy-the-dip setup")
            plan = (
                f"If the price stabilizes and starts climbing after the open, this dip could be a buying "
                f"opportunity. Target roughly +{suspected_profit_pct:.1f}% (about ${suspected_profit_amount:.2f}) "
                f"from your entry, and sell by end of day."
            )
            rank_score = daily.score * 1.2
    else:
        if bullish_trend:
            action = "WATCH_DIP"
            reasons.append("In an uptrend on the daily chart (no pre-market data available yet)")
            plan = "Watch how it trades after the open - a steady climb or a small early dip that recovers are both reasonable entries."
            rank_score = daily.score

    reasons.append(f"Longer-term trend: {daily.action.replace('_', ' ').title()} (score {daily.score:+.2f})")

    return MorningCandidate(
        symbol=symbol,
        action=action,
        price=round(price, 2) if price else daily.price,
        gap_percent=round(gap_pct, 2) if gap_pct is not None else None,
        data_mode=mode,
        daily_trend=daily.action,
        daily_score=daily.score,
        suspected_profit_pct=suspected_profit_pct,
        suspected_profit_amount=suspected_profit_amount,
        plan=plan,
        reasons=reasons,
        rank_score=round(rank_score, 4),
    )
