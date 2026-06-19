"""Same-day (intraday) trading signal engine for currency pairs.

Where `signals.py` reads higher-timeframe candles for swing context, this
module looks at recent 5-minute bars for a scalp / same-session trade:

- VWAP position (are buyers or sellers in control right now?)
- Opening-range breakout/breakdown of the current UTC day
- Short-term momentum (9 vs 20 period EMA crossover on 5-minute bars)
- Intraday RSI (dip-buying / take-profit zones)
- Relative tick-volume spikes

Everything is reported in pips. Because forex has no daily bell, the
"session" context comes from `sessions.py` (which regional sessions are live
and whether the high-liquidity London/New York overlap is active) rather than
a close-out countdown.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import pips
from .indicators import ema, rsi
from .sessions import MarketSession, get_market_session


def vwap(df: pd.DataFrame) -> pd.Series:
    """Volume-weighted average price, cumulative from the start of `df`.

    Uses OANDA tick volume as the weight - the standard intraday-VWAP proxy
    in forex, where true traded volume isn't published.
    """
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    cum_vol = df["Volume"].cumsum()
    cum_vol_price = (typical_price * df["Volume"]).cumsum()
    return cum_vol_price / cum_vol.replace(0, np.nan)


def latest_session(df: pd.DataFrame) -> pd.DataFrame:
    """Return only the bars belonging to the most recent UTC day in `df`.

    Forex trades around the clock, so "today" is defined as the current UTC
    calendar day - the convention OANDA and most brokers use to reset the
    daily range and VWAP anchor.
    """
    if df.empty:
        return df
    last_date = df.index[-1].date()
    mask = [ts.date() == last_date for ts in df.index]
    return df[mask]


@dataclass
class DaySignalResult:
    pair: str
    action: str  # "DAY_BUY" | "DAY_SELL" | "DAY_HOLD"
    score: float
    confidence: float
    price: float
    vwap: float | None
    session_open: float
    session_high: float
    session_low: float
    change_from_open_pips: float
    reasons: list[str] = field(default_factory=list)
    entry: float | None = None
    target: float | None = None
    stop: float | None = None
    target_pips: float | None = None
    stop_pips: float | None = None
    alert: str | None = None  # "TAKE_PROFIT_ZONE" | "STOP_LOSS_ZONE" | None
    session: MarketSession = field(default_factory=get_market_session)


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


def compute_day_signal(pair: str, df: pd.DataFrame) -> DaySignalResult:
    """Compute a same-day Buy/Sell/Hold signal from 5-minute intraday bars."""
    decimals = pips.price_decimals(pair)

    session_df = latest_session(df)
    if session_df is None or len(session_df) < 3:
        raise ValueError(f"Not enough intraday data for {pips.display(pair)} yet today")

    session_df = session_df.copy()
    session_df["vwap"] = vwap(session_df)
    session_df["ema9"] = ema(session_df["Close"], 9)
    session_df["ema20"] = ema(session_df["Close"], 20)
    session_df["rsi9"] = rsi(session_df["Close"], 9)

    last = session_df.iloc[-1]
    prev = session_df.iloc[-2]

    price = float(last["Close"])
    vwap_val = float(last["vwap"]) if not np.isnan(last["vwap"]) else None
    session_open = float(session_df["Open"].iloc[0])
    session_high = float(session_df["High"].max())
    session_low = float(session_df["Low"].min())
    change_from_open_pips = pips.to_pips(pair, price - session_open)

    def fmt(x: float) -> str:
        return f"{x:.{decimals}f}"

    votes: list[tuple[float, float, str]] = []
    alert: str | None = None

    # --- VWAP: who is in control today? ------------------------------------
    if vwap_val:
        if price > vwap_val:
            votes.append((0.6, 1.0, f"Price ({fmt(price)}) is above today's VWAP ({fmt(vwap_val)}) - buyers in control today"))
        else:
            votes.append((-0.6, 1.0, f"Price ({fmt(price)}) is below today's VWAP ({fmt(vwap_val)}) - sellers in control today"))

    # --- Opening range breakout/breakdown (first 30 minutes = 6x 5min bars) -
    if len(session_df) > 6:
        or_high = float(session_df["High"].iloc[:6].max())
        or_low = float(session_df["Low"].iloc[:6].min())
        if price > or_high:
            votes.append((0.8, 1.3, f"Price broke above today's opening-range high ({fmt(or_high)}) - a bullish breakout"))
        elif price < or_low:
            votes.append((-0.8, 1.3, f"Price broke below today's opening-range low ({fmt(or_low)}) - a bearish breakdown"))

    # --- Short-term momentum: 9 vs 20 period EMA on 5-min bars --------------
    ema9, ema20 = last["ema9"], last["ema20"]
    prev_ema9, prev_ema20 = prev["ema9"], prev["ema20"]
    if not np.isnan(ema9) and not np.isnan(ema20):
        crossed_up = not np.isnan(prev_ema9) and prev_ema9 <= prev_ema20 and ema9 > ema20
        crossed_down = not np.isnan(prev_ema9) and prev_ema9 >= prev_ema20 and ema9 < ema20
        if crossed_up:
            votes.append((0.9, 1.4, "Momentum just turned positive (fast average crossed above the slow) - a fresh buy signal"))
        elif crossed_down:
            votes.append((-0.9, 1.4, "Momentum just turned negative (fast average crossed below the slow) - a fresh sell signal"))
        elif ema9 > ema20:
            votes.append((0.4, 0.7, "Short-term momentum is positive"))
        else:
            votes.append((-0.4, 0.7, "Short-term momentum is negative"))

    # --- Intraday RSI: dip-buy / take-profit zones --------------------------
    rsi_val = last["rsi9"]
    if not np.isnan(rsi_val):
        if rsi_val < 30:
            votes.append((0.7, 0.9, f"Short-term RSI is {rsi_val:.0f} - this looks like a dip, often a bounce opportunity for a quick trade"))
        elif rsi_val > 70:
            votes.append((-0.5, 0.9, f"Short-term RSI is {rsi_val:.0f} - looks overextended for now, a common point to lock in gains"))
            alert = "TAKE_PROFIT_ZONE"

    # --- Relative tick-volume spike -----------------------------------------
    if len(session_df) > 6:
        recent_vol = float(last["Volume"])
        avg_vol = float(session_df["Volume"].iloc[:-1].mean())
        if avg_vol > 0 and recent_vol > 1.5 * avg_vol:
            price_change = price - float(prev["Close"])
            if price_change > 0:
                votes.append((0.5, 0.8, "Tick volume just spiked on an up move - strong buying interest right now"))
            elif price_change < 0:
                votes.append((-0.5, 0.8, "Tick volume just spiked on a down move - strong selling pressure right now"))

    if not votes:
        raise ValueError(f"Not enough intraday signal data for {pips.display(pair)} yet")

    weighted_sum = sum(_clip(v) * w for v, w, _ in votes)
    total_weight = sum(w for _, w, _ in votes)
    score = _clip((weighted_sum / total_weight) if total_weight else 0.0)

    if score >= 0.35:
        action = "DAY_BUY"
    elif score <= -0.35:
        action = "DAY_SELL"
    else:
        action = "DAY_HOLD"

    confidence = round(min(100.0, abs(score) * 100 + 10), 1)
    reasons = [r for _, _, r in votes]

    # --- Suspected target/stop, based on today's range so far ---------------
    day_range = session_high - session_low
    if day_range <= 0:
        day_range = pips.from_pips(pair, 10)  # fallback: assume a 10-pip range

    entry = target = stop = None
    target_pips = stop_pips = None
    if action == "DAY_BUY":
        entry = round(price, decimals)
        target = round(price + day_range * 0.5, decimals)
        stop = round(price - day_range * 0.3, decimals)
        target_pips = round(pips.to_pips(pair, target - entry), 1)
        stop_pips = round(pips.to_pips(pair, entry - stop), 1)
    elif action == "DAY_SELL":
        entry = round(price, decimals)
        target = round(price - day_range * 0.5, decimals)
        stop = round(price + day_range * 0.3, decimals)
        target_pips = round(pips.to_pips(pair, entry - target), 1)
        stop_pips = round(pips.to_pips(pair, stop - entry), 1)

    # --- Stop-loss zone: price has dropped meaningfully from the session high
    drawdown = session_high - price
    drawdown_pips = pips.to_pips(pair, drawdown)
    if action != "DAY_BUY" and drawdown_pips > 15:
        alert = "STOP_LOSS_ZONE"
        reasons.append(f"Price has dropped {drawdown_pips:.0f} pips from today's high ({fmt(session_high)}) - consider cutting losses")

    return DaySignalResult(
        pair=pair,
        action=action,
        score=round(score, 4),
        confidence=confidence,
        price=round(price, decimals),
        vwap=round(vwap_val, decimals) if vwap_val else None,
        session_open=round(session_open, decimals),
        session_high=round(session_high, decimals),
        session_low=round(session_low, decimals),
        change_from_open_pips=round(change_from_open_pips, 1),
        reasons=reasons,
        entry=entry,
        target=target,
        stop=stop,
        target_pips=target_pips,
        stop_pips=stop_pips,
        alert=alert,
        session=get_market_session(),
    )
