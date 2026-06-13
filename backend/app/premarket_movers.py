"""Pre-market "movers" scan.

Surfaces stocks that are unusually active *before the open* - ranked by the
size of their overnight price gap and how their trading volume compares to
their own average. This is an honest alternative to "predict which stock
goes from $1 to $30 today": no model can reliably forecast moves of that
size. Instead, this highlights what's *already* moving and *why*, with
explicit risk flags so extreme or illiquid movers aren't mistaken for safe
bets.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .signals import analyze


@dataclass
class MoverCandidate:
    symbol: str
    price: float
    change_percent: float
    data_mode: str
    relative_volume: float | None
    average_volume: float | None
    market_cap: float | None
    momentum_score: float
    daily_trend: str
    risk_flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def evaluate_mover(symbol: str, daily_df: pd.DataFrame, premarket: dict) -> MoverCandidate | None:
    """Return a `MoverCandidate` for `symbol`, or `None` if there isn't a
    meaningful price move to report (e.g. flat with no quote data)."""
    price = premarket.get("price")
    change_pct = premarket.get("change_percent")
    if price is None or change_pct is None:
        return None

    daily = analyze(symbol, daily_df)

    avg_vol = premarket.get("average_volume")
    reg_vol = premarket.get("regular_market_volume")
    rel_vol = (reg_vol / avg_vol) if avg_vol and reg_vol else None

    risk_flags: list[str] = []
    reasons: list[str] = []

    if abs(change_pct) >= 10:
        risk_flags.append("EXTREME_MOVE")
        reasons.append(
            f"Gapping {change_pct:+.1f}% - moves this large often partially reverse once "
            f"regular trading starts, so size any position small"
        )
    if price < 5:
        risk_flags.append("LOW_PRICE")
        reasons.append("Trading under $5/share - lower-priced stocks tend to be more volatile and have wider spreads")
    if avg_vol and avg_vol < 1_000_000:
        risk_flags.append("LOW_LIQUIDITY")
        reasons.append("Average daily volume is relatively low - it may be harder to exit quickly at a fair price")

    momentum_score = abs(change_pct)
    if rel_vol:
        momentum_score += min(rel_vol, 10) * 2
        if rel_vol >= 2:
            reasons.append(f"Recent volume is {rel_vol:.1f}x its average - unusually active")

    if change_pct > 0 and daily.score > 0:
        momentum_score += daily.score * 5
        reasons.append("Also in an uptrend on the daily chart - this gap aligns with the longer-term trend")
    elif change_pct < 0 and daily.score < 0:
        momentum_score += abs(daily.score) * 5
        reasons.append("Also in a downtrend on the daily chart - this gap aligns with the longer-term trend")

    reasons.append(f"{'Up' if change_pct >= 0 else 'Down'} {change_pct:+.2f}% vs. yesterday's close")

    return MoverCandidate(
        symbol=symbol,
        price=round(price, 2),
        change_percent=round(change_pct, 2),
        data_mode=premarket.get("mode", "last_close"),
        relative_volume=round(rel_vol, 2) if rel_vol else None,
        average_volume=avg_vol,
        market_cap=premarket.get("market_cap"),
        momentum_score=round(momentum_score, 2),
        daily_trend=daily.action,
        risk_flags=risk_flags,
        reasons=reasons,
    )
