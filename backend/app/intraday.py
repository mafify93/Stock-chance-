"""Same-day (intraday) trading signal engine.

Unlike `app/signals.py` (multi-day swing signals from daily candles), this
module looks only at *today's* 5-minute bars and is meant for a "buy after
the open, sell before the close" style of trading:

- VWAP position (are buyers or sellers in control today?)
- Opening-range breakout/breakdown (first 30 minutes)
- Short-term momentum (9 vs 20 period EMA crossover on 5-minute bars)
- Intraday RSI (dip-buying / take-profit zones)
- Relative volume spikes

It also tracks the current US market session (pre-market / open /
after-hours / closed) so the app can show countdowns and a forced
"close your position before the bell" alert.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .indicators import ema, rsi

ET = ZoneInfo("America/New_York")

MARKET_OPEN = dtime(9, 30)
MARKET_CLOSE = dtime(16, 0)
PREMARKET_START = dtime(4, 0)
AFTERHOURS_END = dtime(20, 0)

EOD_WARNING_MINUTES = 15


@dataclass
class MarketSession:
    status: str  # "pre_market" | "open" | "after_hours" | "closed"
    now_et: str
    minutes_to_close: int | None = None
    minutes_to_open: int | None = None
    is_weekday: bool = True


def get_market_session(now: datetime | None = None) -> MarketSession:
    now = (now or datetime.now(ET)).astimezone(ET)
    t = now.time()

    if now.weekday() >= 5:  # Saturday/Sunday
        return MarketSession(status="closed", now_et=now.isoformat(), is_weekday=False)

    if MARKET_OPEN <= t < MARKET_CLOSE:
        close_dt = now.replace(hour=16, minute=0, second=0, microsecond=0)
        minutes_to_close = max(0, int((close_dt - now).total_seconds() // 60))
        return MarketSession(status="open", now_et=now.isoformat(), minutes_to_close=minutes_to_close)

    if PREMARKET_START <= t < MARKET_OPEN:
        open_dt = now.replace(hour=9, minute=30, second=0, microsecond=0)
        minutes_to_open = max(0, int((open_dt - now).total_seconds() // 60))
        return MarketSession(status="pre_market", now_et=now.isoformat(), minutes_to_open=minutes_to_open)

    if MARKET_CLOSE <= t < AFTERHOURS_END:
        return MarketSession(status="after_hours", now_et=now.isoformat())

    return MarketSession(status="closed", now_et=now.isoformat())


def vwap(df: pd.DataFrame) -> pd.Series:
    """Volume-weighted average price, cumulative from the start of `df`."""
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    cum_vol = df["Volume"].cumsum()
    cum_vol_price = (typical_price * df["Volume"]).cumsum()
    return cum_vol_price / cum_vol.replace(0, np.nan)


def latest_session(df: pd.DataFrame) -> pd.DataFrame:
    """Return only the bars belonging to the most recent trading session in `df`."""
    if df.empty:
        return df
    last_date = df.index[-1].date()
    mask = [ts.date() == last_date for ts in df.index]
    return df[mask]


@dataclass
class DaySignalResult:
    symbol: str
    action: str  # "DAY_BUY" | "DAY_SELL" | "DAY_HOLD"
    confidence: float
    price: float
    vwap: float | None
    session_open: float
    session_high: float
    session_low: float
    change_from_open_pct: float
    reasons: list[str] = field(default_factory=list)
    entry: float | None = None
    target: float | None = None
    stop: float | None = None
    suspected_profit_pct: float | None = None
    suspected_profit_amount: float | None = None
    alert: str | None = None  # "TAKE_PROFIT_ZONE" | "STOP_LOSS_ZONE" | "EOD_EXIT" | None
    session: MarketSession = field(default_factory=get_market_session)


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


def compute_day_signal(symbol: str, df: pd.DataFrame) -> DaySignalResult:
    """Compute a same-day Buy/Sell/Hold signal from 5-minute intraday bars.

    `df` should be the output of `providers.yahoo.get_intraday_history`
    (5-minute bars, several days, so the most recent session can be
    isolated).
    """
    session_df = latest_session(df)
    if session_df is None or len(session_df) < 3:
        raise ValueError(f"Not enough intraday data for {symbol} yet today")

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
    change_from_open_pct = (price - session_open) / session_open * 100 if session_open else 0.0

    votes: list[tuple[float, float, str]] = []
    alert: str | None = None

    # --- VWAP: are buyers or sellers in control today? ---------------------
    if vwap_val:
        if price > vwap_val:
            votes.append((0.6, 1.0, f"Price (${price:.2f}) is above today's VWAP (${vwap_val:.2f}) - buyers have been in control today"))
        else:
            votes.append((-0.6, 1.0, f"Price (${price:.2f}) is below today's VWAP (${vwap_val:.2f}) - sellers have been in control today"))

    # --- Opening range breakout/breakdown (first 30 minutes = 6x 5min bars) -
    if len(session_df) > 6:
        or_high = float(session_df["High"].iloc[:6].max())
        or_low = float(session_df["Low"].iloc[:6].min())
        if price > or_high:
            votes.append((0.8, 1.3, f"Price broke above the morning's opening range high (${or_high:.2f}) - a bullish breakout"))
        elif price < or_low:
            votes.append((-0.8, 1.3, f"Price broke below the morning's opening range low (${or_low:.2f}) - a bearish breakdown"))

    # --- Short-term momentum: 9 vs 20 period EMA on 5-min bars --------------
    ema9, ema20 = last["ema9"], last["ema20"]
    prev_ema9, prev_ema20 = prev["ema9"], prev["ema20"]
    if not np.isnan(ema9) and not np.isnan(ema20):
        crossed_up = not np.isnan(prev_ema9) and prev_ema9 <= prev_ema20 and ema9 > ema20
        crossed_down = not np.isnan(prev_ema9) and prev_ema9 >= prev_ema20 and ema9 < ema20
        if crossed_up:
            votes.append((0.9, 1.4, "Momentum just turned positive (fast average crossed above the slow average) - a fresh buy signal"))
        elif crossed_down:
            votes.append((-0.9, 1.4, "Momentum just turned negative (fast average crossed below the slow average) - a fresh sell signal"))
        elif ema9 > ema20:
            votes.append((0.4, 0.7, "Short-term momentum is positive"))
        else:
            votes.append((-0.4, 0.7, "Short-term momentum is negative"))

    # --- Intraday RSI: dip-buy / take-profit zones --------------------------
    rsi_val = last["rsi9"]
    if not np.isnan(rsi_val):
        if rsi_val < 30:
            votes.append((0.7, 0.9, f"Short-term RSI is {rsi_val:.0f} - this looks like a dip, often a good bounce opportunity for a quick trade"))
        elif rsi_val > 70:
            votes.append((-0.5, 0.9, f"Short-term RSI is {rsi_val:.0f} - the stock looks 'overheated' for now, a common point to lock in gains"))
            alert = "TAKE_PROFIT_ZONE"

    # --- Relative volume spike -----------------------------------------------
    if len(session_df) > 6:
        recent_vol = float(last["Volume"])
        avg_vol = float(session_df["Volume"].iloc[:-1].mean())
        if avg_vol > 0 and recent_vol > 1.5 * avg_vol:
            price_change = price - float(prev["Close"])
            if price_change > 0:
                votes.append((0.5, 0.8, "Trading volume just spiked on an upward move - strong buying interest right now"))
            elif price_change < 0:
                votes.append((-0.5, 0.8, "Trading volume just spiked on a downward move - strong selling pressure right now"))

    if not votes:
        raise ValueError(f"Not enough intraday signal data for {symbol} yet")

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

    # --- Suspected profit target, based on today's range so far -------------
    day_range = session_high - session_low
    if day_range <= 0:
        day_range = price * 0.01  # fallback: assume a 1% range if flat so far

    entry = target = stop = None
    profit_pct = profit_amt = None
    if action == "DAY_BUY":
        entry = round(price, 2)
        target = round(price + day_range * 0.5, 2)
        stop = round(price - day_range * 0.3, 2)
        profit_amt = round(target - entry, 2)
        profit_pct = round(profit_amt / entry * 100, 2) if entry else None
    elif action == "DAY_SELL":
        entry = round(price, 2)
        target = round(price - day_range * 0.5, 2)
        stop = round(price + day_range * 0.3, 2)
        profit_amt = round(entry - target, 2)
        profit_pct = round(profit_amt / entry * 100, 2) if entry else None

    # --- Stop-loss zone: price has dropped meaningfully from the session high
    drawdown_pct = (session_high - price) / session_high * 100 if session_high else 0.0
    if action != "DAY_BUY" and drawdown_pct > 1.5:
        alert = "STOP_LOSS_ZONE"
        reasons.append(f"Price has dropped {drawdown_pct:.1f}% from today's high (${session_high:.2f}) - consider cutting losses")

    # --- End-of-day exit reminder --------------------------------------------
    session = get_market_session()
    if session.status == "open" and session.minutes_to_close is not None and session.minutes_to_close <= EOD_WARNING_MINUTES:
        alert = "EOD_EXIT"
        reasons.append(f"The market closes in {session.minutes_to_close} minutes - close out same-day positions to avoid holding overnight")

    return DaySignalResult(
        symbol=symbol,
        action=action,
        confidence=confidence,
        price=round(price, 2),
        vwap=round(vwap_val, 2) if vwap_val else None,
        session_open=round(session_open, 2),
        session_high=round(session_high, 2),
        session_low=round(session_low, 2),
        change_from_open_pct=round(change_from_open_pct, 2),
        reasons=reasons,
        entry=entry,
        target=target,
        stop=stop,
        suspected_profit_pct=profit_pct,
        suspected_profit_amount=profit_amt,
        alert=alert,
        session=session,
    )
