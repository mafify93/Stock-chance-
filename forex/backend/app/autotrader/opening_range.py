"""Opening Range Breakout (ORB) signal.

One of the best-documented intraday edges across forex and equities.
The first 15 minutes of NY open (13:00–13:15 UTC) establish a coil — a tight
range while overnight and pre-market orders are still being absorbed. When that
coil breaks with committed flow, it tends to continue.

Entry rules
───────────
1. Time gate: 13:15–17:00 UTC (post-ORB formation, before London stale-out)
2. ORB must be 3–30 pips wide (too tight = noise; too wide = news spike)
3. Price must clear the ORB high/low by a 2-pip buffer (confirmed break, not a wick)
4. Stop: just inside the broken boundary (ORB level ∓ 2 pips)
5. Target: 2× ORB height projected from the entry point

Best pairs: EUR_USD, GBP_USD (highest volume at NY open, cleanest range)
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from .. import pips
from ..intraday import DaySignalResult
from ..sessions import get_market_session

_ORB_START_H = 13
_ORB_WINDOW_MINS = 15       # ORB = first 15 min of NY open
_ENTRY_END_H = 17           # stale after 17:00 UTC
_MIN_RANGE_PIPS = 3.0
_MAX_RANGE_PIPS = 30.0
_BUFFER_PIPS = 2.0
_RR = 2.0                   # target = 2× ORB height


def opening_range_breakout(
    pair: str,
    df_m1: pd.DataFrame,
    now: datetime,
) -> DaySignalResult | None:
    """Evaluate the Opening Range Breakout for one pair.

    Args:
        pair:   OANDA instrument name, e.g. "EUR_USD".
        df_m1:  M1 candle DataFrame (Open/High/Low/Close), DatetimeIndex UTC.
        now:    Current UTC datetime.

    Returns:
        DaySignalResult with all price fields populated, or None.
    """
    if df_m1 is None or len(df_m1) < 20:
        return None

    # ── Time gate ─────────────────────────────────────────────────────────────
    h, m = now.hour, now.minute
    if h < _ORB_START_H or h >= _ENTRY_END_H:
        return None
    if h == _ORB_START_H and m < _ORB_WINDOW_MINS:
        return None  # ORB still forming

    if df_m1.index.tzinfo is None:
        df_m1 = df_m1.copy()
        df_m1.index = df_m1.index.tz_localize("UTC")

    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    orb_start = today.replace(hour=_ORB_START_H, minute=0)
    orb_end = today.replace(hour=_ORB_START_H, minute=_ORB_WINDOW_MINS)

    orb_df = df_m1[(df_m1.index >= orb_start) & (df_m1.index < orb_end)]
    if len(orb_df) < 3:
        return None

    orb_high = float(orb_df["High"].max())
    orb_low = float(orb_df["Low"].min())
    orb_range = orb_high - orb_low
    orb_pips = pips.to_pips(pair, orb_range)

    if not (_MIN_RANGE_PIPS <= orb_pips <= _MAX_RANGE_PIPS):
        return None

    price = float(df_m1["Close"].iloc[-1])
    buffer = pips.from_pips(pair, _BUFFER_PIPS)
    decimals = pips.price_decimals(pair)

    if price > orb_high + buffer:
        action = "DAY_BUY"
        is_buy = True
        entry = round(price, decimals)
        stop = round(orb_high - buffer, decimals)  # just inside the broken top
        target = round(entry + orb_range * _RR, decimals)
        excess_pips = pips.to_pips(pair, price - orb_high)

    elif price < orb_low - buffer:
        action = "DAY_SELL"
        is_buy = False
        entry = round(price, decimals)
        stop = round(orb_low + buffer, decimals)
        target = round(entry - orb_range * _RR, decimals)
        excess_pips = pips.to_pips(pair, orb_low - price)

    else:
        return None  # still inside or barely touching the boundary

    stop_pips_val = round(pips.to_pips(pair, abs(entry - stop)), 1)
    target_pips_val = round(pips.to_pips(pair, abs(target - entry)), 1)

    if stop_pips_val < 1.0:
        return None

    # Confidence: base 70%, boosted the further price has committed beyond the range
    confidence = round(min(88.0, 70.0 + excess_pips * 2.0), 1)

    session_open = float(df_m1["Open"].iloc[0])
    change_pips = round(pips.to_pips(pair, price - session_open), 1)

    reasons = [
        f"ORB Breakout {'above' if is_buy else 'below'} NY open range "
        f"{'high' if is_buy else 'low'} ({orb_high if is_buy else orb_low:.{decimals}f})",
        f"ORB: {orb_pips:.1f}p range  |  break: {excess_pips:.1f}p  |  "
        f"target: {target_pips_val:.1f}p ({_RR:.0f}× range)",
    ]

    return DaySignalResult(
        pair=pair,
        action=action,
        score=round(0.78 if is_buy else -0.78, 4),
        confidence=confidence,
        price=entry,
        vwap=None,
        session_open=round(session_open, decimals),
        session_high=orb_high,
        session_low=orb_low,
        change_from_open_pips=change_pips,
        reasons=reasons,
        entry=entry,
        target=target,
        stop=stop,
        target_pips=target_pips_val,
        stop_pips=stop_pips_val,
        alert=None,
        session=get_market_session(now),
    )
