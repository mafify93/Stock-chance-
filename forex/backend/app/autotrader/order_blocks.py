"""Order Block Reversal signal.

Order blocks are the last opposing candle before a significant impulsive move.
Institutional algorithms frequently return to these zones to re-fill orders
before continuing the trend. Entering as price pulls back into the order block
gives a high-probability setup with a tight stop (just beyond the block's wick).

Uses M15 candles for a cleaner structural view than M1.

Definition
──────────
Bullish Order Block: the last bearish (red) candle immediately before 3 or more
  consecutive bullish candles that move at least MIN_IMPULSE_PIPS total.
  Entry trigger: price retraces back into the OB body.
  Bias: long.

Bearish Order Block: the last bullish (green) candle immediately before 3 or more
  consecutive bearish candles that move at least MIN_IMPULSE_PIPS total.
  Entry trigger: price retraces back into the OB body.
  Bias: short.

Entry rules
───────────
1. Scan the last MAX_LOOKBACK M15 bars for the most recent OB.
2. OB body: [min(Open, Close), max(Open, Close)] of the qualifying candle.
3. Price must be within the OB body at the current moment.
4. Stop: beyond the OB candle's wick extreme + 2 pip buffer.
5. Target: 2× stop distance projected from entry.
6. OB must not be older than MAX_OB_AGE_BARS M15 bars (stale setup).
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from .. import pips
from ..intraday import DaySignalResult
from ..sessions import get_market_session

_MIN_IMPULSE_PIPS = 10.0   # impulse must be at least this wide to qualify
_IMPULSE_CANDLES = 3       # number of same-direction candles that define the impulse
_MAX_LOOKBACK = 40         # bars to scan for an OB
_MAX_OB_AGE_BARS = 20      # OB older than this is considered stale
_BUFFER_PIPS = 2.0
_MIN_STOP_PIPS = 5.0
_RR = 2.0

# Only trade OB setups during active sessions (avoid dead-zone fills)
_SESSION_START_H = 7    # London open
_SESSION_END_H = 20     # NY close


def order_block_reversal(
    pair: str,
    df_m15: pd.DataFrame,
    now: datetime,
) -> DaySignalResult | None:
    """Evaluate the Order Block Reversal for one pair.

    Args:
        pair:    OANDA instrument name, e.g. "EUR_USD".
        df_m15:  M15 candle DataFrame (Open/High/Low/Close), DatetimeIndex UTC.
        now:     Current UTC datetime.

    Returns:
        DaySignalResult with all price fields populated, or None.
    """
    if df_m15 is None or len(df_m15) < _IMPULSE_CANDLES + 2:
        return None

    # ── Session gate ──────────────────────────────────────────────────────────
    if not (_SESSION_START_H <= now.hour < _SESSION_END_H):
        return None

    if df_m15.index.tzinfo is None:
        df_m15 = df_m15.copy()
        df_m15.index = df_m15.index.tz_localize("UTC")

    decimals = pips.price_decimals(pair)
    buffer = pips.from_pips(pair, _BUFFER_PIPS)
    min_impulse = pips.from_pips(pair, _MIN_IMPULSE_PIPS)
    price = float(df_m15["Close"].iloc[-1])

    scan_df = df_m15.iloc[-_MAX_LOOKBACK:].copy()
    result = _find_order_block(scan_df, pair, min_impulse, decimals, buffer)
    if result is None:
        return None

    action, ob_body_low, ob_body_high, stop, ob_age = result

    # ── Price must be inside OB body ──────────────────────────────────────────
    if not (ob_body_low <= price <= ob_body_high):
        return None

    # ── OB freshness check ────────────────────────────────────────────────────
    if ob_age > _MAX_OB_AGE_BARS:
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

    if (is_buy and target <= entry) or (not is_buy and target >= entry):
        return None

    rr = target_pips_val / max(stop_pips_val, 0.1)
    confidence = round(min(84.0, 62.0 + rr * 4.0), 1)

    session_open = float(df_m15["Open"].iloc[0])
    change_pips = round(pips.to_pips(pair, price - session_open), 1)

    reasons = [
        f"Order Block: {'bull' if is_buy else 'bear'} OB reversal (M15)",
        f"OB zone {ob_body_low:.{decimals}f}–{ob_body_high:.{decimals}f}  age {ob_age} bars",
        f"SL {stop_pips_val:.1f}p  TP {target_pips_val:.1f}p  ({rr:.1f}R)",
    ]

    return DaySignalResult(
        pair=pair,
        action=action,
        score=round(0.72 if is_buy else -0.72, 4),
        confidence=confidence,
        price=entry,
        vwap=None,
        session_open=round(session_open, decimals),
        session_high=float(scan_df["High"].max()),
        session_low=float(scan_df["Low"].min()),
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


def _find_order_block(
    df: pd.DataFrame,
    pair: str,
    min_impulse: float,
    decimals: int,
    buffer: float,
) -> tuple[str, float, float, float, int] | None:
    """Scan df (newest slice of M15 bars) for the most recent valid order block.

    Returns (action, ob_body_low, ob_body_high, stop, age_in_bars) or None.
    age_in_bars = bars since the OB candle (how old the zone is).
    """
    n = len(df)

    # Scan newest-first: try each potential OB candle position
    for ob_idx in range(n - _IMPULSE_CANDLES - 1, 0, -1):
        ob_bar = df.iloc[ob_idx]
        ob_open = float(ob_bar["Open"])
        ob_close = float(ob_bar["Close"])
        ob_high = float(ob_bar["High"])
        ob_low = float(ob_bar["Low"])

        ob_is_bearish = ob_close < ob_open
        ob_is_bullish = ob_close > ob_open

        # ── Bullish OB: last bearish candle before bullish impulse ───────────
        if ob_is_bearish:
            impulse_start = ob_idx + 1
            impulse_end = impulse_start + _IMPULSE_CANDLES
            if impulse_end > n:
                continue

            impulse_slice = df.iloc[impulse_start:impulse_end]
            all_bull = all(
                float(r["Close"]) > float(r["Open"])
                for _, r in impulse_slice.iterrows()
            )
            if not all_bull:
                continue

            impulse_size = float(impulse_slice["High"].max()) - float(impulse_slice["Low"].min())
            if impulse_size < min_impulse:
                continue

            ob_body_low = min(ob_open, ob_close)
            ob_body_high = max(ob_open, ob_close)
            stop = ob_low - buffer
            age = n - 1 - ob_idx

            return ("DAY_BUY", ob_body_low, ob_body_high, stop, age)

        # ── Bearish OB: last bullish candle before bearish impulse ───────────
        if ob_is_bullish:
            impulse_start = ob_idx + 1
            impulse_end = impulse_start + _IMPULSE_CANDLES
            if impulse_end > n:
                continue

            impulse_slice = df.iloc[impulse_start:impulse_end]
            all_bear = all(
                float(r["Close"]) < float(r["Open"])
                for _, r in impulse_slice.iterrows()
            )
            if not all_bear:
                continue

            impulse_size = float(impulse_slice["High"].max()) - float(impulse_slice["Low"].min())
            if impulse_size < min_impulse:
                continue

            ob_body_low = min(ob_open, ob_close)
            ob_body_high = max(ob_open, ob_close)
            stop = ob_high + buffer
            age = n - 1 - ob_idx

            return ("DAY_SELL", ob_body_low, ob_body_high, stop, age)

    return None
