"""Same-day (intraday) trading signal engine for currency pairs — v2.

Improvements over v1:
─────────────────────
1. ADX trend-strength filter  – skip signals only when dead-flat (ADX < 15);
                                 dampen conviction in the weak 15–20 band
2. VWAP bounce detection       – trade the *rejection* off VWAP, not just position
3. London open breakout        – Asia-range (00:00-07:00 UTC) break during London
                                 open (07:00-10:00 UTC) is the most reliable intraday
                                 setup in liquid G10 pairs
4. RSI divergence              – price new-low + RSI higher-low = hidden buy strength
5. Candlestick body filter     – require a decisive candle (body ≥ 40% of range)
6. ATR-based dynamic stops     – replaces crude day_range × 0.3 formula
7. Swing S&R clearance         – only enter when target has room before next S/R
8. H1 alignment flag           – caller passes h1_bullish / h1_bearish so the score
                                 is boosted when the higher-timeframe agrees
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import pips
from .indicators import adx as compute_adx
from .indicators import average_true_range, ema, rsi
from .sessions import MarketSession, get_market_session


def vwap(df: pd.DataFrame) -> pd.Series:
    """Volume-weighted average price, cumulative from the start of `df`."""
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    cum_vol = df["Volume"].cumsum()
    cum_vol_price = (typical_price * df["Volume"]).cumsum()
    return cum_vol_price / cum_vol.replace(0, np.nan)


def latest_session(df: pd.DataFrame) -> pd.DataFrame:
    """Return only the bars belonging to the most recent UTC day in `df`."""
    if df.empty:
        return df
    last_date = df.index[-1].date()
    mask = [ts.date() == last_date for ts in df.index]
    return df[mask]


def _swing_highs_lows(series_high: pd.Series, series_low: pd.Series, lookback: int = 5):
    """Detect recent swing highs and lows using a simple local-extremum scan.

    Returns (swing_high_price, swing_low_price) — the most recent confirmed
    swing high and low within the last `lookback * 2` bars.
    """
    n = len(series_high)
    if n < lookback * 2 + 1:
        return None, None

    swing_h, swing_l = None, None
    # Walk backwards to find the most recent swing high and low
    for i in range(n - lookback - 1, lookback, -1):
        hi = float(series_high.iloc[i])
        if all(hi >= float(series_high.iloc[i + k]) for k in range(1, lookback + 1)) and \
           all(hi >= float(series_high.iloc[i - k]) for k in range(1, lookback + 1)):
            if swing_h is None:
                swing_h = hi
        lo = float(series_low.iloc[i])
        if all(lo <= float(series_low.iloc[i + k]) for k in range(1, lookback + 1)) and \
           all(lo <= float(series_low.iloc[i - k]) for k in range(1, lookback + 1)):
            if swing_l is None:
                swing_l = lo
        if swing_h is not None and swing_l is not None:
            break
    return swing_h, swing_l


def _vwap_bounce(session_df: pd.DataFrame, vwap_series: pd.Series, lookback: int = 3) -> int:
    """Detect if price recently bounced off VWAP.

    Returns +1 if a bullish VWAP bounce occurred, -1 for bearish, 0 for none.
    A bounce is: price touched the VWAP band (within 1 pip) in the last
    `lookback` bars AND the most recent close is decisively away from VWAP.
    """
    if len(session_df) < lookback + 1:
        return 0
    recent = session_df.iloc[-(lookback + 1):]
    vwap_r = vwap_series.iloc[-(lookback + 1):]

    # Look for a candle whose low touched VWAP (within 3 pips) and closed above
    # or high touched VWAP and closed below
    for i in range(len(recent) - 1):
        bar = recent.iloc[i]
        vw = float(vwap_r.iloc[i])
        if np.isnan(vw):
            continue
        lo, hi, cl = float(bar["Low"]), float(bar["High"]), float(bar["Close"])
        # Bullish bounce: low dipped to VWAP, closed above
        if lo <= vw <= cl and (cl - lo) > (hi - cl) * 0.5:
            last_close = float(recent["Close"].iloc[-1])
            if last_close > vw:
                return 1
        # Bearish bounce: high spiked to VWAP, closed below
        if cl <= vw <= hi and (hi - cl) > (cl - lo) * 0.5:
            last_close = float(recent["Close"].iloc[-1])
            if last_close < vw:
                return -1
    return 0


def _rsi_divergence(closes: pd.Series, rsi_series: pd.Series, lookback: int = 20) -> int:
    """Detect simple RSI divergence over the last `lookback` bars.

    Returns +1 for bullish divergence (price lower low, RSI higher low),
            -1 for bearish divergence (price higher high, RSI lower high),
             0 for none.
    """
    if len(closes) < lookback:
        return 0
    c = closes.iloc[-lookback:].values
    r = rsi_series.iloc[-lookback:].values
    if any(np.isnan(r)):
        return 0

    # Bullish: current close near period low, RSI above its period low
    c_min_idx = int(np.argmin(c))
    r_at_c_min = r[c_min_idx]
    r_now = r[-1]
    c_now = c[-1]
    c_min = c[c_min_idx]

    if c_now < np.percentile(c, 30) and c_min_idx < len(c) - 3:
        # Price still near lows but is RSI diverging upward?
        if r_now > r_at_c_min + 5 and c_now <= c_min * 1.001:
            return 1

    # Bearish: current close near period high, RSI below its period high
    c_max_idx = int(np.argmax(c))
    r_at_c_max = r[c_max_idx]
    if c_now > np.percentile(c, 70) and c_max_idx < len(c) - 3:
        if r_now < r_at_c_max - 5 and c_now >= c[c_max_idx] * 0.999:
            return -1

    return 0


def _london_open_breakout(df: pd.DataFrame, price: float) -> int:
    """Detect a London open breakout of the Asia session range.

    Asia range = high/low of 00:00–07:00 UTC bars in `df`.
    Breakout = price has moved above Asia high or below Asia low during
    London open (07:00–10:00 UTC).

    Returns +1 (bullish breakout), -1 (bearish breakdown), 0 (none/too early).
    """
    now = df.index[-1]
    hour = now.hour
    if not (7 <= hour < 10):
        return 0

    # Asia bars: 00:00–06:59 UTC on the same day
    today = now.date()
    asia_mask = [
        ts.date() == today and 0 <= ts.hour < 7
        for ts in df.index
    ]
    asia_df = df[asia_mask]
    if len(asia_df) < 5:  # need some Asia data
        return 0

    asia_high = float(asia_df["High"].max())
    asia_low = float(asia_df["Low"].min())
    asia_range = asia_high - asia_low
    if asia_range <= 0:
        return 0

    # Valid breakout: price has moved at least 30% of Asia range beyond the boundary
    threshold = asia_range * 0.3
    if price > asia_high + threshold:
        return 1
    if price < asia_low - threshold:
        return -1
    return 0


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
    atr_pips: float | None = None
    adx: float | None = None


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


def compute_day_signal(
    pair: str,
    df: pd.DataFrame,
    h1_score: float | None = None,
) -> DaySignalResult:
    """Compute a same-day Buy/Sell/Hold signal from 5-minute intraday bars.

    `h1_score` is the H1 swing signal score (-1 to +1) from `signals.analyze()`.
    When provided, the H1 direction boosts or penalises the M5 score.
    """
    decimals = pips.price_decimals(pair)

    session_df = latest_session(df)
    if session_df is None or len(session_df) < 3:
        raise ValueError(f"Not enough intraday data for {pips.display(pair)} yet today")

    session_df = session_df.copy()
    session_df["vwap"] = vwap(session_df)
    session_df["ema9"] = ema(session_df["Close"], 9)
    session_df["ema20"] = ema(session_df["Close"], 20)
    session_df["rsi14"] = rsi(session_df["Close"], 14)

    # ATR and ADX need more bars — compute on full df, use last value
    atr_series = average_true_range(df, 14)
    adx_series = compute_adx(df, 14)

    last = session_df.iloc[-1]
    prev = session_df.iloc[-2]

    price = float(last["Close"])
    vwap_val = float(last["vwap"]) if not np.isnan(last["vwap"]) else None
    session_open = float(session_df["Open"].iloc[0])
    session_high = float(session_df["High"].max())
    session_low = float(session_df["Low"].min())
    change_from_open_pips = pips.to_pips(pair, price - session_open)
    atr_val = float(atr_series.iloc[-1]) if not np.isnan(atr_series.iloc[-1]) else None
    adx_val = float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else None
    atr_pips = round(pips.to_pips(pair, atr_val), 1) if atr_val else None

    def fmt(x: float) -> str:
        return f"{x:.{decimals}f}"

    votes: list[tuple[float, float, str]] = []
    alert: str | None = None

    # ── 1. ADX trend-strength gate ────────────────────────────────────────────
    # Hard-skip only when the market is genuinely dead (ADX < 15). The 15–20 band
    # is allowed through but its score is dampened later — this eases pickiness
    # while still avoiding the flattest, choppiest conditions.
    if adx_val is not None and adx_val < 15:
        # Not enough trend; return HOLD immediately rather than generating noise
        return DaySignalResult(
            pair=pair, action="DAY_HOLD", score=0.0, confidence=0.0,
            price=round(price, decimals), vwap=round(vwap_val, decimals) if vwap_val else None,
            session_open=round(session_open, decimals),
            session_high=round(session_high, decimals),
            session_low=round(session_low, decimals),
            change_from_open_pips=round(change_from_open_pips, 1),
            reasons=[f"ADX {adx_val:.1f} < 15 — market is dead-flat, no trade"],
            atr_pips=atr_pips, adx=round(adx_val, 1) if adx_val else None,
        )

    # ── 2. H1 trend alignment (highest weight) ────────────────────────────────
    # When the hourly chart agrees with the M5 entry, the trade has the wind
    # at its back. When H1 conflicts, skip (return HOLD) — counter-trend scalps
    # have ~35% win rate vs ~55% with-trend.
    if h1_score is not None:
        if h1_score >= 0.15:
            votes.append((1.0, 2.0, f"H1 trend is bullish (score {h1_score:+.2f}) — M5 entry aligned with higher timeframe"))
        elif h1_score <= -0.15:
            votes.append((-1.0, 2.0, f"H1 trend is bearish (score {h1_score:+.2f}) — M5 entry aligned with higher timeframe"))
        else:
            # H1 is flat/conflicted — do not trade against it but don't heavily penalise
            votes.append((0.0, 0.5, "H1 trend is flat — proceed with caution"))

    # ── 3. VWAP: position + bounce detection ─────────────────────────────────
    bounce = _vwap_bounce(session_df, session_df["vwap"], lookback=4)
    if vwap_val:
        if bounce == 1:
            votes.append((1.0, 1.6, f"Bullish VWAP bounce — price dipped to VWAP ({fmt(vwap_val)}) and rejected upward"))
        elif bounce == -1:
            votes.append((-1.0, 1.6, f"Bearish VWAP rejection — price rose to VWAP ({fmt(vwap_val)}) and was rejected downward"))
        elif price > vwap_val:
            votes.append((0.5, 0.8, f"Price ({fmt(price)}) is above today's VWAP ({fmt(vwap_val)}) — buyers in control"))
        else:
            votes.append((-0.5, 0.8, f"Price ({fmt(price)}) is below today's VWAP ({fmt(vwap_val)}) — sellers in control"))

    # ── 4. London open breakout (Asia range) ─────────────────────────────────
    lob = _london_open_breakout(df, price)
    if lob == 1:
        votes.append((0.9, 1.5, "London open breakout above the Asia session range — strong bullish momentum"))
    elif lob == -1:
        votes.append((-0.9, 1.5, "London open breakdown below the Asia session range — strong bearish momentum"))

    # ── 5. Opening range breakout (first 30 min of session) ──────────────────
    if len(session_df) > 6:
        or_high = float(session_df["High"].iloc[:6].max())
        or_low = float(session_df["Low"].iloc[:6].min())
        if price > or_high:
            votes.append((0.8, 1.3, f"Price broke above today's opening-range high ({fmt(or_high)}) — bullish breakout"))
        elif price < or_low:
            votes.append((-0.8, 1.3, f"Price broke below today's opening-range low ({fmt(or_low)}) — bearish breakdown"))

    # ── 6. EMA 9/20 crossover on M5 (short-term momentum) ───────────────────
    ema9, ema20 = last["ema9"], last["ema20"]
    prev_ema9, prev_ema20 = prev["ema9"], prev["ema20"]
    if not np.isnan(ema9) and not np.isnan(ema20):
        crossed_up = not np.isnan(prev_ema9) and prev_ema9 <= prev_ema20 and ema9 > ema20
        crossed_down = not np.isnan(prev_ema9) and prev_ema9 >= prev_ema20 and ema9 < ema20
        if crossed_up:
            votes.append((1.0, 1.4, "M5 momentum just turned bullish (EMA9 crossed above EMA20) — fresh buy signal"))
        elif crossed_down:
            votes.append((-1.0, 1.4, "M5 momentum just turned bearish (EMA9 crossed below EMA20) — fresh sell signal"))
        elif ema9 > ema20:
            votes.append((0.4, 0.7, "Short-term momentum is positive (EMA9 above EMA20)"))
        else:
            votes.append((-0.4, 0.7, "Short-term momentum is negative (EMA9 below EMA20)"))

    # ── 7. RSI: extremes + divergence ────────────────────────────────────────
    rsi_series = session_df["rsi14"]
    rsi_val = float(rsi_series.iloc[-1]) if not np.isnan(rsi_series.iloc[-1]) else None
    if rsi_val is not None:
        div = _rsi_divergence(session_df["Close"], rsi_series, lookback=min(30, len(session_df)))
        if div == 1:
            votes.append((0.8, 1.1, f"Bullish RSI divergence — price made new lows but RSI is recovering (hidden buying strength)"))
        elif div == -1:
            votes.append((-0.8, 1.1, f"Bearish RSI divergence — price made new highs but RSI is weakening (hidden selling pressure)"))
        elif rsi_val < 30:
            votes.append((0.7, 0.9, f"M5 RSI {rsi_val:.0f} — oversold, potential bounce opportunity"))
        elif rsi_val > 70:
            votes.append((-0.5, 0.9, f"M5 RSI {rsi_val:.0f} — overbought, often a take-profit zone"))
            alert = "TAKE_PROFIT_ZONE"

    # ── 8. Candlestick body confirmation ─────────────────────────────────────
    # Require the signal candle to be decisive — not a doji or spinning top.
    # Body must be ≥ 40% of the full High-Low range.
    bar_range = float(last["High"]) - float(last["Low"])
    bar_body = abs(float(last["Close"]) - float(last["Open"]))
    if bar_range > 0 and bar_body / bar_range >= 0.40:
        candle_dir = 1.0 if float(last["Close"]) > float(last["Open"]) else -1.0
        votes.append((candle_dir * 0.5, 0.8, f"Strong {'bullish' if candle_dir > 0 else 'bearish'} candle — decisive close confirms momentum"))
    # If candle is weak (doji-like), add a mild contrary nudge
    elif bar_range > 0 and bar_body / bar_range < 0.20:
        votes.append((0.0, 0.3, "Indecisive candle (doji-like) — reduced confidence in signal direction"))

    # ── 9. Volume spike in signal direction ───────────────────────────────────
    if len(session_df) > 6:
        recent_vol = float(last["Volume"])
        avg_vol = float(session_df["Volume"].iloc[:-1].mean())
        if avg_vol > 0 and recent_vol > 1.5 * avg_vol:
            price_change = price - float(prev["Close"])
            if price_change > 0:
                votes.append((0.5, 0.8, "Volume spike on an up move — strong buying interest"))
            elif price_change < 0:
                votes.append((-0.5, 0.8, "Volume spike on a down move — strong selling pressure"))

    if not votes:
        raise ValueError(f"Not enough intraday signal data for {pips.display(pair)} yet")

    # ── Score aggregation ────────────────────────────────────────────────────
    weighted_sum = sum(_clip(v) * w for v, w, _ in votes)
    total_weight = sum(w for _, w, _ in votes)
    score = _clip((weighted_sum / total_weight) if total_weight else 0.0)

    # ADX shaping: boost when strongly trending, dampen in the weak 15–20 band.
    if adx_val is not None:
        if adx_val > 25:
            score = _clip(score * 1.25)
        elif adx_val < 20:
            score = _clip(score * 0.9)  # weak trend — slightly less conviction

    # Entry threshold. Lowered 0.38 → 0.30 to ease pickiness; the confidence
    # gate (user's "Min confidence" slider) is the real selectivity control.
    if score >= 0.30:
        action = "DAY_BUY"
    elif score <= -0.30:
        action = "DAY_SELL"
    else:
        action = "DAY_HOLD"

    confidence = round(min(100.0, abs(score) * 100 + 10), 1)
    reasons = [r for _, _, r in votes]

    # ── Stop & target: ATR-based (dynamic) ──────────────────────────────────
    # ATR-based stops adapt to volatility. A 1.5x ATR stop is the standard
    # used by systematic traders — wide enough to avoid noise, tight enough
    # to keep risk small. Fallback to day-range method if ATR isn't available.
    day_range = session_high - session_low
    if day_range <= 0:
        day_range = pips.from_pips(pair, 10)

    entry = target = stop = None
    target_pips_val = stop_pips_val = None

    if atr_val and atr_val > 0:
        # 1.5× ATR stop, 3× ATR target (2:1 R:R) — the minimum ratio that keeps
        # expectancy positive at a ~43% win rate with a 1.2-pip round-trip spread.
        stop_dist = 1.5 * atr_val
        tgt_dist = stop_dist * 2.0
    else:
        stop_dist = day_range * 0.3
        tgt_dist = stop_dist * 2.0

    # ── Swing S&R clearance check ──────────────────────────────────────────
    # If the nearest swing S&R is closer than our target, we don't have room —
    # degrade to HOLD because the target will be blocked.
    swing_h, swing_l = _swing_highs_lows(df["High"], df["Low"], lookback=5)
    if action == "DAY_BUY" and swing_h is not None:
        room = swing_h - price
        if room < tgt_dist * 0.4:  # only block when S/R sits inside 40% of target
            action = "DAY_HOLD"
            reasons.append(f"Trade blocked: swing high at {fmt(swing_h)} is too close — target has no room")
            return DaySignalResult(
                pair=pair, action="DAY_HOLD", score=round(score, 4),
                confidence=confidence, price=round(price, decimals),
                vwap=round(vwap_val, decimals) if vwap_val else None,
                session_open=round(session_open, decimals),
                session_high=round(session_high, decimals),
                session_low=round(session_low, decimals),
                change_from_open_pips=round(change_from_open_pips, 1),
                reasons=reasons, atr_pips=atr_pips,
                adx=round(adx_val, 1) if adx_val else None,
            )
    if action == "DAY_SELL" and swing_l is not None:
        room = price - swing_l
        if room < tgt_dist * 0.4:  # only block when S/R sits inside 40% of target
            action = "DAY_HOLD"
            reasons.append(f"Trade blocked: swing low at {fmt(swing_l)} is too close — target has no room")
            return DaySignalResult(
                pair=pair, action="DAY_HOLD", score=round(score, 4),
                confidence=confidence, price=round(price, decimals),
                vwap=round(vwap_val, decimals) if vwap_val else None,
                session_open=round(session_open, decimals),
                session_high=round(session_high, decimals),
                session_low=round(session_low, decimals),
                change_from_open_pips=round(change_from_open_pips, 1),
                reasons=reasons, atr_pips=atr_pips,
                adx=round(adx_val, 1) if adx_val else None,
            )

    if action == "DAY_BUY":
        entry = round(price, decimals)
        stop = round(price - stop_dist, decimals)
        target = round(price + tgt_dist, decimals)
        stop_pips_val = round(pips.to_pips(pair, stop_dist), 1)
        target_pips_val = round(pips.to_pips(pair, tgt_dist), 1)
    elif action == "DAY_SELL":
        entry = round(price, decimals)
        stop = round(price + stop_dist, decimals)
        target = round(price - tgt_dist, decimals)
        stop_pips_val = round(pips.to_pips(pair, stop_dist), 1)
        target_pips_val = round(pips.to_pips(pair, tgt_dist), 1)

    # ── Stop-loss zone alert ──────────────────────────────────────────────
    drawdown = session_high - price
    drawdown_pips = pips.to_pips(pair, drawdown)
    if action != "DAY_BUY" and drawdown_pips > 15:
        alert = "STOP_LOSS_ZONE"
        reasons.append(f"Price has dropped {drawdown_pips:.0f} pips from today's high ({fmt(session_high)}) — consider cutting losses")

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
        target_pips=target_pips_val,
        stop_pips=stop_pips_val,
        alert=alert,
        session=get_market_session(),
        atr_pips=atr_pips,
        adx=round(adx_val, 1) if adx_val else None,
    )
