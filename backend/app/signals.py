"""Rule-based technical analysis signal engine.

IMPORTANT: This produces data-driven technical analysis signals based on
well-known indicators. It is NOT a guarantee of future price movement and
should not be treated as financial advice. It is meant as a decision-support
tool, combining multiple indicators into a transparent, explainable score.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .indicators import compute_all_indicators


Action = str  # "STRONG_BUY" | "BUY" | "HOLD" | "SELL" | "STRONG_SELL"


@dataclass
class SignalResult:
    symbol: str
    action: Action
    score: float  # -1.0 (strong sell) .. +1.0 (strong buy)
    confidence: float  # 0..100
    price: float
    reasons: list[str] = field(default_factory=list)
    indicators: dict = field(default_factory=dict)
    levels: dict = field(default_factory=dict)


def _score_to_action(score: float) -> Action:
    if score >= 0.5:
        return "STRONG_BUY"
    if score >= 0.15:
        return "BUY"
    if score <= -0.5:
        return "STRONG_SELL"
    if score <= -0.15:
        return "SELL"
    return "HOLD"


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


def analyze(symbol: str, df: pd.DataFrame) -> SignalResult:
    """Compute indicators and a composite buy/sell/hold signal for one symbol.

    `df` must contain at least ~210 rows of daily OHLCV data for the
    SMA-200 / ADX indicators to be meaningful.
    """
    if df is None or df.empty:
        raise ValueError(f"No price data available for {symbol}")

    data = compute_all_indicators(df)
    last = data.iloc[-1]
    prev = data.iloc[-2] if len(data) > 1 else last

    price = float(last["Close"])
    votes: list[tuple[float, float, str]] = []  # (vote in [-1,1], weight, reason)

    # --- Trend: price vs moving averages -------------------------------
    if not np.isnan(last.get("sma_50", np.nan)):
        if price > last["sma_50"]:
            votes.append((1.0, 1.0, f"Price (${price:.2f}) is above its 50-day average (${last['sma_50']:.2f}) - uptrend"))
        else:
            votes.append((-1.0, 1.0, f"Price (${price:.2f}) is below its 50-day average (${last['sma_50']:.2f}) - downtrend"))

    if not np.isnan(last.get("sma_200", np.nan)):
        if price > last["sma_200"]:
            votes.append((1.0, 1.2, f"Price is above its 200-day average (${last['sma_200']:.2f}) - long-term uptrend"))
        else:
            votes.append((-1.0, 1.2, f"Price is below its 200-day average (${last['sma_200']:.2f}) - long-term downtrend"))

    # Golden / death cross (50 vs 200)
    if not np.isnan(last.get("sma_50", np.nan)) and not np.isnan(last.get("sma_200", np.nan)):
        if not np.isnan(prev.get("sma_50", np.nan)) and not np.isnan(prev.get("sma_200", np.nan)):
            crossed_up = prev["sma_50"] <= prev["sma_200"] and last["sma_50"] > last["sma_200"]
            crossed_down = prev["sma_50"] >= prev["sma_200"] and last["sma_50"] < last["sma_200"]
            if crossed_up:
                votes.append((1.0, 1.5, "Golden cross: 50-day average just crossed above the 200-day average"))
            elif crossed_down:
                votes.append((-1.0, 1.5, "Death cross: 50-day average just crossed below the 200-day average"))

    # --- Momentum: RSI ---------------------------------------------------
    rsi_val = last.get("rsi_14", np.nan)
    if not np.isnan(rsi_val):
        if rsi_val < 30:
            votes.append((1.0, 1.3, f"RSI is {rsi_val:.1f} (oversold, < 30) - potential rebound"))
        elif rsi_val > 70:
            votes.append((-1.0, 1.3, f"RSI is {rsi_val:.1f} (overbought, > 70) - potential pullback"))
        elif rsi_val < 45:
            votes.append((-0.3, 0.6, f"RSI is {rsi_val:.1f} - leaning weak (bearish momentum)"))
        elif rsi_val > 55:
            votes.append((0.3, 0.6, f"RSI is {rsi_val:.1f} - leaning strong (bullish momentum)"))

    # --- MACD --------------------------------------------------------------
    macd_val, macd_sig = last.get("macd", np.nan), last.get("macd_signal", np.nan)
    prev_macd, prev_sig = prev.get("macd", np.nan), prev.get("macd_signal", np.nan)
    if not np.isnan(macd_val) and not np.isnan(macd_sig):
        crossed_up = (not np.isnan(prev_macd)) and prev_macd <= prev_sig and macd_val > macd_sig
        crossed_down = (not np.isnan(prev_macd)) and prev_macd >= prev_sig and macd_val < macd_sig
        if crossed_up:
            votes.append((1.0, 1.4, "MACD just crossed above its signal line - bullish momentum shift"))
        elif crossed_down:
            votes.append((-1.0, 1.4, "MACD just crossed below its signal line - bearish momentum shift"))
        elif macd_val > macd_sig:
            votes.append((0.5, 0.7, "MACD is above its signal line - positive momentum"))
        else:
            votes.append((-0.5, 0.7, "MACD is below its signal line - negative momentum"))

    # --- Bollinger Bands ---------------------------------------------------
    bb_lower, bb_upper = last.get("bb_lower", np.nan), last.get("bb_upper", np.nan)
    if not np.isnan(bb_lower) and not np.isnan(bb_upper):
        if price <= bb_lower:
            votes.append((1.0, 1.0, f"Price is at/below the lower Bollinger Band (${bb_lower:.2f}) - possibly oversold"))
        elif price >= bb_upper:
            votes.append((-1.0, 1.0, f"Price is at/above the upper Bollinger Band (${bb_upper:.2f}) - possibly overbought"))

    # --- Stochastic Oscillator ----------------------------------------------
    k, d = last.get("stoch_k", np.nan), last.get("stoch_d", np.nan)
    if not np.isnan(k):
        if k < 20:
            votes.append((1.0, 0.8, f"Stochastic %K is {k:.1f} (< 20) - oversold"))
        elif k > 80:
            votes.append((-1.0, 0.8, f"Stochastic %K is {k:.1f} (> 80) - overbought"))

    # --- Volume confirmation -------------------------------------------------
    vol, vol_avg = last.get("Volume", np.nan), last.get("volume_sma_20", np.nan)
    if not np.isnan(vol_avg) and vol_avg > 0:
        price_change = price - float(prev["Close"])
        if vol > 1.5 * vol_avg:
            if price_change > 0:
                votes.append((0.6, 0.9, "Volume is well above average on an up move - confirms buyers in control"))
            elif price_change < 0:
                votes.append((-0.6, 0.9, "Volume is well above average on a down move - confirms sellers in control"))

    # --- Trend strength (ADX) - amplifies the trend votes -------------------
    adx_val = last.get("adx_14", np.nan)
    trend_multiplier = 1.0
    if not np.isnan(adx_val):
        if adx_val > 25:
            trend_multiplier = 1.25
        elif adx_val < 15:
            trend_multiplier = 0.75

    if not votes:
        raise ValueError(f"Not enough history to compute indicators for {symbol}")

    weighted_sum = sum(_clip(v) * w for v, w in ((v, w) for v, w, _ in votes))
    total_weight = sum(w for _, w, _ in votes)
    raw_score = weighted_sum / total_weight if total_weight else 0.0
    score = _clip(raw_score * trend_multiplier)

    action = _score_to_action(score)
    confidence = round(min(100.0, abs(score) * 100 + 5), 1)

    reasons = [r for _, _, r in votes]

    atr = float(last.get("atr_14", np.nan)) if not np.isnan(last.get("atr_14", np.nan)) else None
    levels: dict = {}
    if atr:
        if score > 0:
            levels = {
                "suggested_entry": round(price, 2),
                "stop_loss": round(price - 1.5 * atr, 2),
                "take_profit": round(price + 3 * atr, 2),
                "risk_reward": 2.0,
            }
        elif score < 0:
            levels = {
                "suggested_exit": round(price, 2),
                "stop_loss_short": round(price + 1.5 * atr, 2),
                "take_profit_short": round(price - 3 * atr, 2),
                "risk_reward": 2.0,
            }

    indicators_out = {
        "rsi_14": _round(rsi_val),
        "macd": _round(macd_val),
        "macd_signal": _round(macd_sig),
        "sma_50": _round(last.get("sma_50")),
        "sma_200": _round(last.get("sma_200")),
        "bb_upper": _round(bb_upper),
        "bb_lower": _round(bb_lower),
        "stoch_k": _round(k),
        "stoch_d": _round(d),
        "adx_14": _round(adx_val),
        "atr_14": _round(atr),
    }

    return SignalResult(
        symbol=symbol,
        action=action,
        score=round(score, 4),
        confidence=confidence,
        price=round(price, 2),
        reasons=reasons,
        indicators=indicators_out,
        levels=levels,
    )


def _round(value, ndigits: int = 2):
    if value is None:
        return None
    try:
        if np.isnan(value):
            return None
    except TypeError:
        pass
    return round(float(value), ndigits)
