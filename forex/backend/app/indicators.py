"""Technical indicator calculations used by the signal engines.

All functions take a pandas DataFrame with columns:
    Open, High, Low, Close, Volume
indexed by time, and return either a pandas Series or a dict of Series.

For forex the "Volume" column is OANDA's *tick volume* (the number of price
changes in the bar). It isn't true traded volume, but it's a well-established
proxy for activity and works the same way in the volume-confirmation rules.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_value = 100 - (100 / (1 + rs))
    rsi_value = rsi_value.where(avg_loss != 0, 100)
    return rsi_value


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, pd.Series]:
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return {"macd": macd_line, "signal": signal_line, "hist": histogram}


def bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0) -> dict[str, pd.Series]:
    mid = sma(series, period)
    std = series.rolling(window=period, min_periods=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return {"mid": mid, "upper": upper, "lower": lower}


def stochastic_oscillator(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> dict[str, pd.Series]:
    low_min = df["Low"].rolling(window=k_period, min_periods=k_period).min()
    high_max = df["High"].rolling(window=k_period, min_periods=k_period).max()
    denom = (high_max - low_min).replace(0, np.nan)
    percent_k = 100 * (df["Close"] - low_min) / denom
    percent_d = percent_k.rolling(window=d_period, min_periods=d_period).mean()
    return {"k": percent_k, "d": percent_d}


def average_true_range(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    up_move = df["High"].diff()
    down_move = -df["Low"].diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    atr = average_true_range(df, period)
    plus_dm_s = pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    minus_dm_s = pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    plus_di = 100 * (plus_dm_s / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm_s / atr.replace(0, np.nan))

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def volume_sma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    return sma(df["Volume"], period)


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with all indicator columns appended."""
    out = df.copy()
    close = out["Close"]

    out["sma_20"] = sma(close, 20)
    out["sma_50"] = sma(close, 50)
    out["sma_200"] = sma(close, 200)
    out["ema_12"] = ema(close, 12)
    out["ema_26"] = ema(close, 26)
    out["rsi_14"] = rsi(close, 14)

    macd_vals = macd(close)
    out["macd"] = macd_vals["macd"]
    out["macd_signal"] = macd_vals["signal"]
    out["macd_hist"] = macd_vals["hist"]

    bb = bollinger_bands(close)
    out["bb_mid"] = bb["mid"]
    out["bb_upper"] = bb["upper"]
    out["bb_lower"] = bb["lower"]

    stoch = stochastic_oscillator(out)
    out["stoch_k"] = stoch["k"]
    out["stoch_d"] = stoch["d"]

    out["atr_14"] = average_true_range(out)
    out["adx_14"] = adx(out)
    out["volume_sma_20"] = volume_sma(out)

    return out
