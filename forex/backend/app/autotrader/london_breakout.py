"""London Open Breakout signal.

The Asian session (22:00–07:00 UTC) trades in a tight, low-liquidity range.
When London opens (07:00 UTC), real institutional flow enters and price tends
to break out of the Asian range and trend for 1–3 hours.

This is one of the best-documented structural edges in retail forex:
- It's driven by a real market event (London open flow), not lagging indicators.
- Win rates of 48–55% with 2:1 RR are achievable on EUR/USD and GBP/USD.
- It fails on JPY pairs during Asia-heavy sessions and on low-volatility days.

Entry rules:
1. Time gate: 07:00–10:00 UTC only (stale after 10:00)
2. Asian range must be ≥ 8 pips (skip dead/flat sessions)
3. Price must clear Asian high/low by a 2-pip buffer (confirmed break, not a wick)
4. ATR of Asian session bars must be ≥ 5 pips (skip extremely choppy micro-ranges)
5. Recommended pairs: EUR_USD, GBP_USD only (tightest spreads, cleanest breakouts)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .. import pips
from ..intraday import DaySignalResult
from ..sessions import get_market_session


def london_open_breakout(
    pair: str,
    df: pd.DataFrame,
    now: datetime,
    breakout_buffer_pips: float = 2.0,
    min_asian_range_pips: float = 8.0,
    min_atr_pips: float = 5.0,
) -> DaySignalResult | None:
    """Evaluate the London Open Breakout for one pair.

    Args:
        pair: OANDA instrument name (e.g. "EUR_USD")
        df: M5 candle DataFrame with columns High/Low/Close/Open/Volume,
            DatetimeIndex in UTC. Should cover at least 14 hours of history
            so the full Asian session is included.
        now: current UTC datetime
        breakout_buffer_pips: price must clear Asian range by this many pips
            to confirm the break (filters out wicks and false starts)
        min_asian_range_pips: skip if Asian session was too flat/dead
        min_atr_pips: skip if per-bar volatility was too choppy (tight bars
            that whipsaw both directions)

    Returns:
        DaySignalResult if a valid breakout is detected, None otherwise.
    """
    if df.empty or len(df) < 10:
        return None

    # ── Time gate: only active 07:00–10:00 UTC ───────────────────────────────
    hour_utc = now.hour
    if not (7 <= hour_utc < 10):
        return None

    # ── Isolate Asian session bars ────────────────────────────────────────────
    # Asian session = 22:00 UTC yesterday → 07:00 UTC today
    today_open = now.replace(hour=7, minute=0, second=0, microsecond=0)
    asian_start = today_open - timedelta(hours=9)  # 22:00 UTC previous day

    if df.index.tzinfo is None:
        df = df.copy()
        df.index = df.index.tz_localize("UTC")

    asian_df = df[(df.index >= asian_start) & (df.index < today_open)]
    if len(asian_df) < 5:
        return None  # not enough Asian session bars

    asian_high = float(asian_df["High"].max())
    asian_low = float(asian_df["Low"].min())
    asian_range = asian_high - asian_low
    asian_range_pips = pips.to_pips(pair, asian_range)

    if asian_range_pips < min_asian_range_pips:
        return None  # flat Asian session — no meaningful range to break

    # ── ATR filter: skip choppy micro-ranging sessions ────────────────────────
    true_ranges = asian_df["High"] - asian_df["Low"]
    atr_pips = pips.to_pips(pair, float(true_ranges.mean()))
    if atr_pips < min_atr_pips:
        return None  # bars too small — will whipsaw on entry

    # ── Current price and breakout detection ──────────────────────────────────
    price = float(df["Close"].iloc[-1])
    buffer = pips.from_pips(pair, breakout_buffer_pips)
    decimals = pips.price_decimals(pair)

    if price > asian_high + buffer:
        action = "DAY_BUY"
        is_buy = True
        # Stop sits just inside the Asian range (2 pips below Asian high).
        # This is the tightest logical stop — if price falls back inside the
        # range the breakout has failed.
        stop = round(asian_high - pips.from_pips(pair, 2.0), decimals)
        excess_pips = pips.to_pips(pair, price - asian_high)

    elif price < asian_low - buffer:
        action = "DAY_SELL"
        is_buy = False
        stop = round(asian_low + pips.from_pips(pair, 2.0), decimals)
        excess_pips = pips.to_pips(pair, asian_low - price)

    else:
        return None  # price still inside the Asian range — no breakout yet

    entry = round(price, decimals)
    stop_pips_val = round(pips.to_pips(pair, abs(entry - stop)), 1)
    target_pips_val = round(stop_pips_val * 2.0, 1)  # 2:1 RR
    delta_tp = pips.from_pips(pair, target_pips_val)
    target = round((entry + delta_tp) if is_buy else (entry - delta_tp), decimals)

    # ── Confidence: base 72%, boosted by how clean/strong the break is ───────
    # A clean break (price far beyond Asian range) is more likely to follow
    # through than a price that just barely cleared the buffer.
    confidence = round(min(90.0, 72.0 + excess_pips * 1.5), 1)

    reasons = [
        f"London Open Breakout: price {'above' if is_buy else 'below'} "
        f"Asian session {'high' if is_buy else 'low'} "
        f"({asian_high if is_buy else asian_low:.{decimals}f})",
        f"Asian session range: {asian_range_pips:.1f} pips  |  "
        f"break distance: {excess_pips:.1f} pips  |  "
        f"avg bar ATR: {atr_pips:.1f} pips",
    ]

    return DaySignalResult(
        pair=pair,
        action=action,
        score=round(0.8 if is_buy else -0.8, 4),
        confidence=confidence,
        price=entry,
        vwap=None,
        session_open=round(float(df["Open"].iloc[0]), decimals),
        session_high=asian_high,
        session_low=asian_low,
        change_from_open_pips=round(pips.to_pips(pair, price - float(df["Open"].iloc[0])), 1),
        reasons=reasons,
        entry=entry,
        target=target,
        stop=stop,
        target_pips=target_pips_val,
        stop_pips=stop_pips_val,
        alert=None,
        session=get_market_session(now),
    )
