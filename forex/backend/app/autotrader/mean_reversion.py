"""Range-regime mean-reversion strategy (Bollinger fade).

The momentum/EMA strategy earns its money on strong trend days and bleeds
during ranges — live results and the day-by-day backtest breakdown both show
it. This module is the complement: it trades ONLY when the market is ranging
(ADX below a ceiling) and fades statistical extremes back toward the mean.

Setup (classic band-fade, deliberately simple):
  LONG  when the bar closes at/below the lower Bollinger(20, 2) band with
        RSI(2) deeply oversold — price stretched far below the local mean
        in a non-trending market tends to snap back toward it.
  SHORT when the bar closes at/above the upper band with RSI(2) overbought.

Regime gate: ADX(14) must be BELOW `adx_max` — the inverse of the momentum
strategy's gate, so the two are naturally complementary: EMA holds in ranges
(its own ADX < threshold gate), this holds in trends.

Exit geometry: reversion targets the mean, not a runaway move — the caller
should pair the returned stop with a ~1:1 reward ratio (cfg.mr_rr_ratio),
NOT the trend strategy's 2:1. High win-rate / modest-win profile.
"""
from __future__ import annotations

import pandas as pd

from .. import pips
from ..indicators import adx as adx_fn, average_true_range, bollinger_bands, rsi
from ..intraday import DaySignalResult, latest_session


def mean_reversion_signal(
    pair: str,
    df: pd.DataFrame,
    adx_max: float = 20.0,
) -> DaySignalResult | None:
    """Return a DAY_BUY/DAY_SELL reversion signal, or None if no setup.

    `df` is an M5 OHLCV frame of CLOSED bars (same contract as
    compute_day_signal). Returns None rather than DAY_HOLD so callers can
    fall through to other strategies.
    """
    if df is None or len(df) < 40:
        return None

    close = df["Close"]
    bb = bollinger_bands(close, 20, 2.0)
    mid = float(bb["mid"].iloc[-1])
    upper = float(bb["upper"].iloc[-1])
    lower = float(bb["lower"].iloc[-1])
    if pd.isna(mid) or pd.isna(upper) or upper <= mid:
        return None
    sigma = (upper - mid) / 2.0
    if sigma <= 0:
        return None

    # Regime gate: only fade in a ranging market. In a trend, band touches are
    # continuation, not reversion — fading them is catching a falling knife.
    adx_val = adx_fn(df, 14).dropna()
    if len(adx_val) == 0 or float(adx_val.iloc[-1]) >= adx_max:
        return None

    price = float(close.iloc[-1])
    rsi2 = rsi(close, 2).dropna()
    if len(rsi2) == 0:
        return None
    rsi2_val = float(rsi2.iloc[-1])

    z = (price - mid) / sigma  # how many band-sigmas price sits from the mean

    action: str | None = None
    if z <= -2.0 and rsi2_val <= 10:
        action = "DAY_BUY"
    elif z >= 2.0 and rsi2_val >= 90:
        action = "DAY_SELL"
    if action is None:
        return None

    # Confidence: deeper stretch beyond the band + more extreme RSI = higher.
    depth = abs(z) - 2.0
    rsi_extreme = rsi2_val <= 5 or rsi2_val >= 95
    confidence = min(90.0, 62.0 + min(18.0, depth * 30.0) + (6.0 if rsi_extreme else 0.0))

    # Stop: 1.5 ATR beyond entry (engine/backtest clamp to min/max_stop_pips).
    atr = average_true_range(df, 14).dropna()
    atr_pips = pips.to_pips(pair, float(atr.iloc[-1])) if len(atr) else 8.0
    stop_pips = round(max(6.0, 1.5 * atr_pips), 1)

    decimals = pips.price_decimals(pair)
    delta = pips.from_pips(pair, stop_pips)
    stop = round(price - delta, decimals) if action == "DAY_BUY" else round(price + delta, decimals)

    session_df = latest_session(df)
    session_open = float(session_df["Open"].iloc[0]) if len(session_df) else price
    session_high = float(session_df["High"].max()) if len(session_df) else price
    session_low = float(session_df["Low"].min()) if len(session_df) else price

    direction = "below lower" if action == "DAY_BUY" else "above upper"
    return DaySignalResult(
        pair=pair,
        action=action,
        score=max(-1.0, min(1.0, -z / 3.0)),  # stretched low → positive (buy) score
        confidence=round(confidence, 1),
        price=round(price, decimals),
        vwap=None,
        session_open=round(session_open, decimals),
        session_high=round(session_high, decimals),
        session_low=round(session_low, decimals),
        change_from_open_pips=round(pips.to_pips(pair, price - session_open), 1),
        reasons=[
            f"Mean reversion: close {direction} Bollinger band (z={z:+.2f}), "
            f"RSI(2)={rsi2_val:.0f}, ADX={float(adx_val.iloc[-1]):.1f} (ranging) — "
            f"fading the extreme back toward the mean"
        ],
        entry=round(price, decimals),
        target=None,           # caller derives target from stop × mr_rr_ratio
        stop=stop,
        target_pips=None,
        stop_pips=stop_pips,
    )
