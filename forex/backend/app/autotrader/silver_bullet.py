"""ICT Silver Bullet signal.

Three 1-hour institutional windows each trading day — moments when the
algorithmic market-makers create Fair Value Gaps (FVGs) in their quest for
liquidity before committing to a directional run. Entering at the FVG
midpoint on the first pullback gives a clean risk structure: tight stop at
the swing extreme of the impulse, target at the next liquidity pool.

Windows (UTC — London/NY summer hours):
  07:00–08:00  London open impulse
  14:00–15:00  NY morning setup (≈ 10:00 ET)
  18:00–19:00  NY afternoon (3 PM ET)

Entry rules
───────────
1. Within an active window, scan the last 60 M1 bars for the most recent
   bullish or bearish FVG created INSIDE the window.
   FVG definition: three consecutive candles where
     – Bullish: candle[i-1].High < candle[i+1].Low  (gap in lows)
     – Bearish: candle[i-1].Low  > candle[i+1].High (gap in highs)
2. The FVG must be preceded by at least 2 candles in the same direction
   (confirms an impulsive move, not a drift).
3. Price must have pulled back INTO the FVG (between fvg_low and fvg_high).
4. Stop: beyond the swing extreme of the impulse leg + 2 pip buffer.
5. Target: 2× stop distance from entry.
6. Skip if stop < 3 pips (avoids data artefacts).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from .. import pips
from ..intraday import DaySignalResult
from ..sessions import get_market_session

# Silver Bullet windows (hour_start, hour_end) — all UTC
_WINDOWS: list[tuple[int, int]] = [
    (7, 8),   # London open
    (14, 15), # NY morning
    (18, 19), # NY afternoon
]

_BUFFER_PIPS = 2.0
_MIN_STOP_PIPS = 3.0
_RR = 2.0
_IMPULSE_CANDLES = 2   # require at least this many same-direction candles before the FVG
_MAX_FVG_AGE_MINS = 55 # FVG must have formed in the current window (not a prior one)


def silver_bullet(
    pair: str,
    df_m1: pd.DataFrame,
    now: datetime,
) -> DaySignalResult | None:
    """Evaluate the ICT Silver Bullet for one pair.

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
    active_window = None
    for w_start, w_end in _WINDOWS:
        if w_start <= now.hour < w_end:
            active_window = (w_start, w_end)
            break
    if active_window is None:
        return None

    if df_m1.index.tzinfo is None:
        df_m1 = df_m1.copy()
        df_m1.index = df_m1.index.tz_localize("UTC")

    # Window bars only — FVG must have formed inside this window
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_start_dt = today.replace(hour=active_window[0], minute=0)
    window_df = df_m1[df_m1.index >= window_start_dt].copy()

    if len(window_df) < 4:
        return None  # window just started, not enough bars yet

    decimals = pips.price_decimals(pair)
    buffer = pips.from_pips(pair, _BUFFER_PIPS)
    price = float(df_m1["Close"].iloc[-1])

    # ── Find the most recent FVG inside the window ────────────────────────────
    result = _find_fvg_in_window(window_df, pair, decimals, buffer)
    if result is None:
        return None

    action, entry, stop, fvg_low, fvg_high = result

    # ── Price must be inside the FVG to take the trade ───────────────────────
    if not (fvg_low <= price <= fvg_high):
        return None

    entry = round(price, decimals)
    stop = round(stop, decimals)

    stop_pips_val = round(pips.to_pips(pair, abs(entry - stop)), 1)
    if stop_pips_val < _MIN_STOP_PIPS:
        return None

    is_buy = action == "DAY_BUY"
    target_pips_val = round(stop_pips_val * _RR, 1)
    delta_tp = pips.from_pips(pair, target_pips_val)
    target = round((entry + delta_tp) if is_buy else (entry - delta_tp), decimals)

    # Sanity check
    if (is_buy and target <= entry) or (not is_buy and target >= entry):
        return None

    rr = target_pips_val / max(stop_pips_val, 0.1)
    confidence = round(min(86.0, 65.0 + rr * 4.0), 1)

    window_label = f"{active_window[0]:02d}:00–{active_window[1]:02d}:00 UTC"
    session_open = float(df_m1["Open"].iloc[0])
    change_pips = round(pips.to_pips(pair, price - session_open), 1)

    reasons = [
        f"ICT Silver Bullet: {'bull' if is_buy else 'bear'} FVG at {window_label}",
        f"FVG zone {fvg_low:.{decimals}f}–{fvg_high:.{decimals}f}  entry @ {entry:.{decimals}f}",
        f"SL {stop_pips_val:.1f}p  TP {target_pips_val:.1f}p  ({rr:.1f}R)",
    ]

    return DaySignalResult(
        pair=pair,
        action=action,
        score=round(0.76 if is_buy else -0.76, 4),
        confidence=confidence,
        price=entry,
        vwap=None,
        session_open=round(session_open, decimals),
        session_high=float(window_df["High"].max()),
        session_low=float(window_df["Low"].min()),
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


# ── Private helpers ───────────────────────────────────────────────────────────


def _find_fvg_in_window(
    df: pd.DataFrame,
    pair: str,
    decimals: int,
    buffer: float,
) -> tuple[str, float, float, float, float] | None:
    """Scan df (window bars only) for the most recent impulsive FVG.

    Returns (action, entry, stop, fvg_low, fvg_high) or None.
    entry = FVG midpoint, stop = swing extreme + buffer.
    """
    # Need at least 3 bars for FVG detection (i-1, i, i+1)
    if len(df) < 3:
        return None

    # Scan newest-first: find the most recent FVG
    for i in range(len(df) - 2, 0, -1):
        c_prev = df.iloc[i - 1]
        c_curr = df.iloc[i]
        c_next = df.iloc[i + 1]

        # ── Bullish FVG: gap between c_prev.High and c_next.Low ──────────────
        if float(c_prev["High"]) < float(c_next["Low"]):
            fvg_low = float(c_prev["High"])
            fvg_high = float(c_next["Low"])

            # Require impulse: at least _IMPULSE_CANDLES bullish candles ending at c_curr
            impulse_ok = _count_impulse_candles(df, i, is_bull=True) >= _IMPULSE_CANDLES
            if not impulse_ok:
                continue

            # Stop: swing low of the impulse leg
            swing_low = _swing_low(df, i)
            stop = swing_low - buffer if swing_low is not None else float(c_prev["Low"]) - buffer
            entry = (fvg_low + fvg_high) / 2.0

            return ("DAY_BUY", round(entry, decimals), stop, fvg_low, fvg_high)

        # ── Bearish FVG: gap between c_prev.Low and c_next.High ──────────────
        if float(c_prev["Low"]) > float(c_next["High"]):
            fvg_low = float(c_next["High"])
            fvg_high = float(c_prev["Low"])

            impulse_ok = _count_impulse_candles(df, i, is_bull=False) >= _IMPULSE_CANDLES
            if not impulse_ok:
                continue

            swing_high = _swing_high(df, i)
            stop = swing_high + buffer if swing_high is not None else float(c_prev["High"]) + buffer
            entry = (fvg_low + fvg_high) / 2.0

            return ("DAY_SELL", round(entry, decimals), stop, fvg_low, fvg_high)

    return None


def _count_impulse_candles(df: pd.DataFrame, end_idx: int, is_bull: bool) -> int:
    """Count consecutive same-direction candles ending at end_idx (inclusive)."""
    count = 0
    for i in range(end_idx, -1, -1):
        row = df.iloc[i]
        if is_bull:
            if float(row["Close"]) > float(row["Open"]):
                count += 1
            else:
                break
        else:
            if float(row["Close"]) < float(row["Open"]):
                count += 1
            else:
                break
    return count


def _swing_low(df: pd.DataFrame, before_idx: int) -> float | None:
    """Return the lowest Low in df[:before_idx] (the impulse leg)."""
    if before_idx < 1:
        return None
    return float(df.iloc[:before_idx]["Low"].min())


def _swing_high(df: pd.DataFrame, before_idx: int) -> float | None:
    """Return the highest High in df[:before_idx] (the impulse leg)."""
    if before_idx < 1:
        return None
    return float(df.iloc[:before_idx]["High"].max())
