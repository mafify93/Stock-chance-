"""Feature engineering shared by training and inference for the ML
direction model.

`build_feature_frame` takes a DataFrame that already has indicator columns
from `app.indicators.compute_all_indicators` and returns a DataFrame of
purely numeric, scale-independent features (ratios and oscillator values
rather than raw prices) suitable for a tree-based classifier. Trees handle
NaNs and differing scales natively, so no imputation/scaling is needed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_NAMES: list[str] = [
    "rsi_14",
    "macd_hist",
    "bb_position",
    "stoch_k",
    "stoch_d",
    "adx_14",
    "atr_pct",
    "price_vs_sma50",
    "price_vs_sma200",
    "sma50_vs_sma200",
    "volume_ratio",
    "return_1d",
    "return_5d",
    "return_10d",
    "return_20d",
    "return_60d",
    "return_120d",
    "dist_52w_high",
    "dist_52w_low",
    "vol_regime",
    "volume_trend",
    "bb_width",
    "momentum_accel",
    "rsi_slope",
    "macd_hist_slope",
]


def build_feature_frame(data: pd.DataFrame) -> pd.DataFrame:
    """`data` must have indicator columns from `compute_all_indicators`."""
    close = data["Close"]
    out = pd.DataFrame(index=data.index)

    out["rsi_14"] = data["rsi_14"]
    out["macd_hist"] = data["macd_hist"]

    bb_range = (data["bb_upper"] - data["bb_lower"]).replace(0, np.nan)
    out["bb_position"] = (close - data["bb_lower"]) / bb_range

    out["stoch_k"] = data["stoch_k"]
    out["stoch_d"] = data["stoch_d"]
    out["adx_14"] = data["adx_14"]
    out["atr_pct"] = data["atr_14"] / close

    out["price_vs_sma50"] = close / data["sma_50"] - 1
    out["price_vs_sma200"] = close / data["sma_200"] - 1
    out["sma50_vs_sma200"] = data["sma_50"] / data["sma_200"] - 1

    out["volume_ratio"] = data["Volume"] / data["volume_sma_20"]

    out["return_1d"] = close.pct_change(1)
    out["return_5d"] = close.pct_change(5)
    out["return_10d"] = close.pct_change(10)
    out["return_20d"] = close.pct_change(20)

    # Multi-factor expansion: longer-horizon momentum, 52-week position,
    # volatility/volume regime, Bollinger width, and oscillator slopes. All
    # self-contained (computable from this symbol's own OHLCV + indicators) so
    # they backfill cleanly for training.
    out["return_60d"] = close.pct_change(60)
    out["return_120d"] = close.pct_change(120)

    rolling_high = close.rolling(252, min_periods=20).max().replace(0, np.nan)
    rolling_low = close.rolling(252, min_periods=20).min().replace(0, np.nan)
    out["dist_52w_high"] = close / rolling_high - 1
    out["dist_52w_low"] = close / rolling_low - 1

    atr_mean = data["atr_14"].rolling(60, min_periods=10).mean().replace(0, np.nan)
    out["vol_regime"] = data["atr_14"] / atr_mean

    vol_sma_mean = data["volume_sma_20"].rolling(60, min_periods=10).mean().replace(0, np.nan)
    out["volume_trend"] = data["volume_sma_20"] / vol_sma_mean

    out["bb_width"] = (data["bb_upper"] - data["bb_lower"]) / close.replace(0, np.nan)

    out["momentum_accel"] = close.pct_change(5) - close.pct_change(20)
    out["rsi_slope"] = data["rsi_14"] - data["rsi_14"].shift(5)
    out["macd_hist_slope"] = data["macd_hist"] - data["macd_hist"].shift(3)

    return out[FEATURE_NAMES]


def build_labels(data: pd.DataFrame, horizon: int) -> pd.Series:
    """1.0 if the close price `horizon` trading days later is higher than
    today's close, 0.0 otherwise. NaN for the final `horizon` rows."""
    future_close = data["Close"].shift(-horizon)
    label = (future_close > data["Close"]).astype(float)
    label[future_close.isna()] = np.nan
    return label
