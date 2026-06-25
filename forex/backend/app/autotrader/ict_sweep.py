"""ICT Session Sweep + FVG Reversal signal.

NY 9 AM setup (ICT / Smart Money Concepts):
  1. Mark Asia session (00:00–07:00 UTC) and London session (07:00–13:00 UTC) high/low.
  2. At NY open (13:00–15:00 UTC), scan M1 bars for a sweep of one of those levels.
     A sweep = wick clears the level by ≥ MIN_SWEEP_PIPS AND candle closes back inside.
  3. After the sweep candle, locate the nearest bullish/bearish Fair Value Gap on M1.
  4. Enter when current price is near the FVG midpoint.
  5. Stop: beyond the sweep-candle extreme + 2 pip buffer.
  6. Target: opposite session level (liquidity draw); fall back to 2 × stop if no
     reachable level qualifies.

Why this works
──────────────
Institutional algorithms hunt the highs and lows left by the Asian and London
sessions to collect resting orders before committing to a directional move. The
wick that sweeps those levels is the trigger; the Fair Value Gap it creates is
the order block. Entering at the FVG and targeting the opposite pool of liquidity
gives a well-defined risk structure (sweep extreme = hard stop) and a clear
directional narrative.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from .. import pips
from ..intraday import DaySignalResult
from ..sessions import get_market_session

# ── Constants ─────────────────────────────────────────────────────────────────

# NY open monitoring window (UTC): 13:00–15:00 (≈ 09:00–11:00 ET summer)
_WINDOW_START_H = 13
_WINDOW_END_H = 15

# Sweep must wick beyond the level by at least this many pips to be "real"
_MIN_SWEEP_PIPS = 1.5

# After the sweep candle, scan up to this many M1 bars forward for an FVG
_FVG_LOOKBACK = 30

# Minimum R-multiple the chosen target must offer relative to the stop distance
_MIN_RR = 1.5


# ── Public API ────────────────────────────────────────────────────────────────


def ict_session_sweep(
    pair: str,
    df_m1: pd.DataFrame,
    now: datetime,
    current_price: float | None = None,
) -> DaySignalResult | None:
    """Evaluate the ICT Session Sweep + FVG setup for one pair.

    Args:
        pair:          OANDA instrument name, e.g. "EUR_USD".
        df_m1:         M1 candle DataFrame (Open/High/Low/Close), DatetimeIndex UTC.
                       Should contain ≥ 750 bars (≈ 12.5 h) to cover the full
                       Asian and London sessions.
        now:           Current UTC datetime.
        current_price: Current mid price; falls back to last M1 close when None.

    Returns:
        DaySignalResult with all price fields populated, or None when no valid
        setup is found.
    """
    if df_m1 is None or len(df_m1) < 100:
        return None

    # ── Time gate ─────────────────────────────────────────────────────────────
    if not (_WINDOW_START_H <= now.hour < _WINDOW_END_H):
        return None

    # Normalise to UTC-aware index
    if df_m1.index.tzinfo is None:
        df_m1 = df_m1.copy()
        df_m1.index = df_m1.index.tz_localize("UTC")

    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    asia_end = today_midnight.replace(hour=7)
    london_end = today_midnight.replace(hour=13)

    # ── Session ranges ────────────────────────────────────────────────────────
    asia_df = df_m1[(df_m1.index >= today_midnight) & (df_m1.index < asia_end)]
    london_df = df_m1[(df_m1.index >= asia_end) & (df_m1.index < london_end)]

    if len(asia_df) < 10 or len(london_df) < 10:
        return None

    asia_high = float(asia_df["High"].max())
    asia_low = float(asia_df["Low"].min())
    london_high = float(london_df["High"].max())
    london_low = float(london_df["Low"].min())

    # ── Monitoring-window bars (13:00 UTC → now) ─────────────────────────────
    window_start = today_midnight.replace(hour=_WINDOW_START_H)
    window_df = df_m1[df_m1.index >= window_start].copy()
    if len(window_df) < 3:
        return None

    min_sweep = pips.from_pips(pair, _MIN_SWEEP_PIPS)
    decimals = pips.price_decimals(pair)

    # Levels to check: (name, price, is_high)
    levels = [
        ("asia_high", asia_high, True),
        ("asia_low", asia_low, False),
        ("london_high", london_high, True),
        ("london_low", london_low, False),
    ]

    # ── Find the most recent sweep across all levels ──────────────────────────
    best: dict | None = None  # {sweep_idx, action, level_name, level_price, entry, stop}

    for level_name, level_price, is_high in levels:
        result = _find_sweep_and_fvg(window_df, level_price, is_high, pair, min_sweep, decimals)
        if result is None:
            continue
        sweep_idx, entry, stop = result

        # Counter-directional action: swept high → bearish; swept low → bullish
        action = "DAY_SELL" if is_high else "DAY_BUY"

        if best is None or sweep_idx > best["sweep_idx"]:
            best = {
                "sweep_idx": sweep_idx,
                "action": action,
                "level_name": level_name,
                "level_price": level_price,
                "entry": entry,
                "stop": stop,
            }

    if best is None:
        return None

    is_buy = best["action"] == "DAY_BUY"
    entry = best["entry"]
    stop = best["stop"]

    # ── Current-price slippage guard ──────────────────────────────────────────
    price = current_price if current_price is not None else float(df_m1["Close"].iloc[-1])
    slippage_pips = pips.to_pips(pair, abs(price - entry))
    if slippage_pips > 5.0:
        return None  # price moved too far from the FVG — setup is stale

    # Use current price as the actual entry
    entry = round(price, decimals)
    stop = round(stop, decimals)

    stop_pips_val = round(pips.to_pips(pair, abs(entry - stop)), 1)
    if stop_pips_val < 3.0:
        return None  # stop too tight — likely a data artefact

    # ── Target selection ─────────────────────────────────────────────────────
    target = _liquidity_draw(
        is_buy, entry, stop,
        asia_high, asia_low, london_high, london_low,
        best["level_name"], pair, decimals,
    )

    if target is not None:
        target = round(target, decimals)
        target_pips_val = round(pips.to_pips(pair, abs(target - entry)), 1)
    else:
        target_pips_val = round(stop_pips_val * 2.0, 1)
        delta_tp = pips.from_pips(pair, target_pips_val)
        target = round((entry + delta_tp) if is_buy else (entry - delta_tp), decimals)

    # Sanity-check target direction
    if (is_buy and target <= entry) or (not is_buy and target >= entry):
        return None

    rr = target_pips_val / max(stop_pips_val, 0.1)
    confidence = round(min(88.0, 68.0 + rr * 3.0), 1)

    level_name = best["level_name"]
    level_price = best["level_price"]
    session_open = float(df_m1["Open"].iloc[0])
    change_pips = round(pips.to_pips(pair, price - session_open), 1)

    reasons = [
        f"ICT Sweep: {'bear' if not is_buy else 'bull'} reversal after sweeping "
        f"{level_name.replace('_', ' ')} ({level_price:.{decimals}f})",
        f"Asia H/L {asia_high:.{decimals}f}/{asia_low:.{decimals}f}  "
        f"London H/L {london_high:.{decimals}f}/{london_low:.{decimals}f}",
        f"FVG entry @ {entry:.{decimals}f}  SL {stop_pips_val:.1f}p  "
        f"TP {target_pips_val:.1f}p  ({rr:.1f}R)",
    ]

    return DaySignalResult(
        pair=pair,
        action=best["action"],
        score=round(0.75 if is_buy else -0.75, 4),
        confidence=confidence,
        price=entry,
        vwap=None,
        session_open=round(session_open, decimals),
        session_high=max(asia_high, london_high),
        session_low=min(asia_low, london_low),
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


def _find_sweep_and_fvg(
    df: pd.DataFrame,
    level: float,
    is_high: bool,
    pair: str,
    min_sweep: float,
    decimals: int,
) -> tuple[int, float, float] | None:
    """Scan df for the most recent sweep of `level`, then locate the first FVG
    after that sweep candle.

    Returns (sweep_bar_pos_in_df, fvg_entry_price, stop_price) or None.
    """
    # Find the most recent sweep (scan newest → oldest)
    sweep_pos = None
    for i in range(len(df) - 1, -1, -1):
        row = df.iloc[i]
        if is_high:
            # High sweep: wick above level, close back below
            if row["High"] >= level + min_sweep and row["Close"] < level:
                sweep_pos = i
                break
        else:
            # Low sweep: wick below level, close back above
            if row["Low"] <= level - min_sweep and row["Close"] > level:
                sweep_pos = i
                break

    if sweep_pos is None:
        return None

    sweep_bar = df.iloc[sweep_pos]
    is_long_setup = not is_high  # swept a high → bear; swept a low → bull

    # Stop: beyond the sweep candle's extreme + 2 pip buffer
    buffer = pips.from_pips(pair, 2.0)
    if is_high:
        stop = float(sweep_bar["High"]) + buffer
    else:
        stop = float(sweep_bar["Low"]) - buffer

    # Search for an FVG starting from the bar AFTER the sweep
    fvg_entry = None
    scan_end = min(len(df) - 1, sweep_pos + _FVG_LOOKBACK)

    for i in range(sweep_pos + 1, scan_end):
        if i < 1:
            continue
        c0 = df.iloc[i - 1]
        c2 = df.iloc[i + 1] if i + 1 < len(df) else None
        if c2 is None:
            break

        if is_long_setup:
            # Bullish FVG: gap between c0.High and c2.Low
            if c0["High"] < c2["Low"]:
                fvg_entry = (float(c0["High"]) + float(c2["Low"])) / 2.0
                break
        else:
            # Bearish FVG: gap between c0.Low and c2.High
            if c0["Low"] > c2["High"]:
                fvg_entry = (float(c0["Low"]) + float(c2["High"])) / 2.0
                break

    # If no FVG found, use the close of the sweep candle as proxy entry
    if fvg_entry is None:
        fvg_entry = float(sweep_bar["Close"])

    return (sweep_pos, round(fvg_entry, decimals), stop)


def _liquidity_draw(
    is_long: bool,
    entry: float,
    stop: float,
    asia_high: float,
    asia_low: float,
    london_high: float,
    london_low: float,
    swept_level_name: str,
    pair: str,
    decimals: int,
) -> float | None:
    """Select the best liquidity-draw target.

    If we swept a low (bullish), target the highs of the other session.
    If we swept a high (bearish), target the lows of the other session.
    The chosen target must offer at least MIN_RR × stop distance.
    """
    min_move = pips.from_pips(pair, pips.to_pips(pair, abs(entry - stop)) * _MIN_RR)

    if is_long:
        # Targets: highs above entry
        if "asia" in swept_level_name:
            candidates = [london_high, asia_high]
        else:
            candidates = [asia_high, london_high]
        min_target = entry + min_move
        for t in candidates:
            if t >= min_target:
                return round(t, decimals)
    else:
        # Targets: lows below entry
        if "asia" in swept_level_name:
            candidates = [london_low, asia_low]
        else:
            candidates = [asia_low, london_low]
        max_target = entry - min_move
        for t in candidates:
            if t <= max_target:
                return round(t, decimals)

    return None  # caller falls back to 2R
