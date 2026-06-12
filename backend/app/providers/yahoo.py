"""Free, no-API-key data provider backed by Yahoo Finance.

Covers virtually any publicly traded ticker (US and international
equities, ETFs, indices, crypto, FX) via the `yfinance` library and
Yahoo's public search endpoint. Because this is an unofficial/free
interface, results are cached briefly and requests are rate-limit
tolerant.
"""
from __future__ import annotations

import logging

import httpx
import pandas as pd
import yfinance as yf

from ..cache import cache

logger = logging.getLogger(__name__)

SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
_HEADERS = {"User-Agent": "Mozilla/5.0 (StockChance/1.0)"}

HISTORY_TTL = 60 * 5  # 5 minutes for daily candles
QUOTE_TTL = 15  # near real-time quote
SEARCH_TTL = 60 * 60  # symbol search rarely changes
INTRADAY_TTL = 30  # 30 seconds for 5-minute intraday candles
PREMARKET_TTL = 60  # 1 minute for pre/post-market snapshot


def get_history(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Return OHLCV history for `symbol`. Cached briefly to limit upstream calls."""
    cache_key = f"history:{symbol}:{period}:{interval}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval, auto_adjust=True)
    if df is None or df.empty:
        raise ValueError(f"No historical data found for symbol '{symbol}'")

    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    cache.set(cache_key, df, HISTORY_TTL)
    return df


def get_intraday_history(symbol: str, period: str = "5d", interval: str = "5m") -> pd.DataFrame:
    """Return intraday OHLCV bars (default: 5-minute bars for the last 5 sessions)."""
    cache_key = f"intraday:{symbol}:{period}:{interval}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval, auto_adjust=True, prepost=False)
    if df is None or df.empty:
        raise ValueError(f"No intraday data found for symbol '{symbol}'")

    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    cache.set(cache_key, df, INTRADAY_TTL)
    return df


def get_premarket_info(symbol: str) -> dict:
    """Best-effort pre-market / after-hours snapshot.

    Returns a dict with `mode` set to one of:
      - "pre_market": pre-market trading is active, `price`/`change_percent`
        reflect the pre-market quote
      - "after_hours": after-hours trading is active, reflects the
        post-market quote
      - "last_close": neither is available; `change_percent` reflects the
        most recent regular-session change
    """
    cache_key = f"premarket:{symbol}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    ticker = yf.Ticker(symbol)
    info: dict = {}
    try:
        info = ticker.get_info()
    except Exception:  # noqa: BLE001
        logger.debug("Could not fetch ticker.info for %s", symbol, exc_info=True)

    previous_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
    result = {
        "symbol": symbol.upper(),
        "previous_close": previous_close,
        "regular_market_price": info.get("regularMarketPrice"),
        "regular_market_change_percent": info.get("regularMarketChangePercent"),
    }

    if info.get("preMarketPrice") is not None:
        result["mode"] = "pre_market"
        result["price"] = info.get("preMarketPrice")
        result["change_percent"] = info.get("preMarketChangePercent")
    elif info.get("postMarketPrice") is not None:
        result["mode"] = "after_hours"
        result["price"] = info.get("postMarketPrice")
        result["change_percent"] = info.get("postMarketChangePercent")
    else:
        result["mode"] = "last_close"
        result["price"] = info.get("regularMarketPrice")
        result["change_percent"] = info.get("regularMarketChangePercent")

    cache.set(cache_key, result, PREMARKET_TTL)
    return result


def get_quote(symbol: str) -> dict:
    """Return a near real-time quote snapshot for `symbol`."""
    cache_key = f"quote:{symbol}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    ticker = yf.Ticker(symbol)
    fast = ticker.fast_info
    last_price = fast.get("lastPrice")
    prev_close = fast.get("previousClose")

    if last_price is None:
        raise ValueError(f"No quote data found for symbol '{symbol}'")

    change = None
    change_percent = None
    if prev_close:
        change = last_price - prev_close
        change_percent = (change / prev_close) * 100

    quote = {
        "symbol": symbol.upper(),
        "price": round(float(last_price), 4),
        "previous_close": round(float(prev_close), 4) if prev_close else None,
        "change": round(float(change), 4) if change is not None else None,
        "change_percent": round(float(change_percent), 4) if change_percent is not None else None,
        "day_high": fast.get("dayHigh"),
        "day_low": fast.get("dayLow"),
        "open": fast.get("open"),
        "volume": fast.get("lastVolume"),
        "market_cap": fast.get("marketCap"),
        "currency": fast.get("currency"),
        "exchange": fast.get("exchange"),
        "fifty_day_average": fast.get("fiftyDayAverage"),
        "two_hundred_day_average": fast.get("twoHundredDayAverage"),
        "year_high": fast.get("yearHigh"),
        "year_low": fast.get("yearLow"),
    }
    cache.set(cache_key, quote, QUOTE_TTL)
    return quote


def search_symbols(query: str, limit: int = 10) -> list[dict]:
    """Search for tickers by name or symbol across all asset types."""
    cache_key = f"search:{query.lower()}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    resp = httpx.get(
        SEARCH_URL,
        params={"q": query, "quotesCount": limit, "newsCount": 0},
        headers=_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    quotes = resp.json().get("quotes", [])

    results = [
        {
            "symbol": q.get("symbol"),
            "name": q.get("longname") or q.get("shortname"),
            "exchange": q.get("exchDisp"),
            "type": q.get("quoteType"),
            "sector": q.get("sector"),
        }
        for q in quotes
        if q.get("symbol")
    ]
    cache.set(cache_key, results, SEARCH_TTL)
    return results


def get_analyst_outlook(symbol: str) -> dict:
    """Best-effort analyst recommendation/price-target summary from Yahoo Finance.

    This data is freely bundled with Yahoo's ticker pages; availability and
    fields vary by ticker and may be missing for smaller/international names.
    """
    cache_key = f"analyst:{symbol}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    ticker = yf.Ticker(symbol)
    result: dict = {"recommendation_key": None, "target_mean_price": None, "target_high_price": None,
                     "target_low_price": None, "number_of_analyst_opinions": None, "recommendations_summary": None}

    try:
        info = ticker.get_info()
        result["recommendation_key"] = info.get("recommendationKey")
        result["target_mean_price"] = info.get("targetMeanPrice")
        result["target_high_price"] = info.get("targetHighPrice")
        result["target_low_price"] = info.get("targetLowPrice")
        result["number_of_analyst_opinions"] = info.get("numberOfAnalystOpinions")
    except Exception:  # noqa: BLE001 - best effort, info endpoint is flaky
        logger.debug("Could not fetch ticker.info for %s", symbol, exc_info=True)

    try:
        rec = ticker.recommendations
        if rec is not None and not rec.empty:
            latest = rec.iloc[0].to_dict()
            result["recommendations_summary"] = latest
    except Exception:  # noqa: BLE001
        logger.debug("Could not fetch recommendations for %s", symbol, exc_info=True)

    cache.set(cache_key, result, HISTORY_TTL)
    return result
