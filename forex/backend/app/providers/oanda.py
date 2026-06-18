"""Thin client for OANDA's v20 REST API - both market data AND trading.

OANDA is unusual (and convenient) in that the same account/token provides
*both* the price data the signal engines need (candles, live pricing) and the
order execution. So this one module is the app's data feed and its broker.

This backend never stores OANDA credentials: the iOS app keeps the user's
API token and account ID in its Keychain and sends them on each request via
the `Oanda-Api-Token` / `Oanda-Account-Id` headers (plus `Oanda-Api-Env:
practice|live` to pick which environment to hit), which this module forwards
directly to OANDA.

`PRACTICE_BASE_URL` talks to OANDA's fxPractice (demo) environment - virtual
money, no real risk. `LIVE_BASE_URL` talks to the user's real fxTrade account
and places REAL orders with REAL money - the iOS app gates this behind an
explicit acknowledgment and a per-order confirmation.

Units convention: a positive `units` order goes LONG the base currency, a
negative `units` order goes SHORT. 100,000 units = 1 standard lot, 10,000 =
1 mini lot, 1,000 = 1 micro lot.
"""
from __future__ import annotations

import httpx
import pandas as pd

from .. import pips
from ..cache import cache

PRACTICE_BASE_URL = "https://api-fxpractice.oanda.com/v3"
LIVE_BASE_URL = "https://api-fxtrade.oanda.com/v3"

CANDLES_TTL = 20      # seconds - intraday candles move fast
CANDLES_HTF_TTL = 60  # higher-timeframe candles can cache a little longer
PRICING_TTL = 5


class OandaError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept-Datetime-Format": "RFC3339",
    }


def _request(method: str, path: str, token: str, base_url: str, **kwargs) -> dict:
    url = f"{base_url}{path}"
    try:
        resp = httpx.request(method, url, headers=_headers(token), timeout=20, **kwargs)
    except httpx.HTTPError as exc:
        raise OandaError(502, f"Could not reach OANDA: {exc}") from exc

    if resp.status_code >= 400:
        detail = resp.text
        try:
            body = resp.json()
            detail = body.get("errorMessage") or body.get("message") or detail
        except Exception:  # noqa: BLE001
            pass
        raise OandaError(resp.status_code, detail)

    if not resp.content:
        return {}
    return resp.json()


# --- Market data --------------------------------------------------------------


def get_candles(
    pair: str,
    token: str,
    granularity: str = "H1",
    count: int = 300,
    base_url: str = PRACTICE_BASE_URL,
) -> pd.DataFrame:
    """OHLCV candles for `pair` as a pandas DataFrame indexed by UTC time.

    `granularity` is an OANDA code: "M5" (5-minute), "M15", "H1", "H4", "D",
    etc. The "Volume" column is OANDA tick volume.
    """
    instrument = pips.normalize(pair)
    ttl = CANDLES_TTL if granularity.startswith("M") else CANDLES_HTF_TTL
    cache_key = f"candles:{instrument}:{granularity}:{count}:{base_url}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    data = _request(
        "GET",
        f"/instruments/{instrument}/candles",
        token,
        base_url,
        params={"granularity": granularity, "count": count, "price": "M"},
    )
    candles = [c for c in data.get("candles", []) if c.get("complete", True)]
    if not candles:
        raise ValueError(f"No candle data returned for {pips.display(pair)}")

    rows = []
    index = []
    for c in candles:
        mid = c["mid"]
        index.append(pd.to_datetime(c["time"]))
        rows.append(
            {
                "Open": float(mid["o"]),
                "High": float(mid["h"]),
                "Low": float(mid["l"]),
                "Close": float(mid["c"]),
                "Volume": float(c.get("volume", 0)),
            }
        )
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(index))
    cache.set(cache_key, df, ttl)
    return df


def get_pricing(
    pairs: list[str],
    token: str,
    account_id: str,
    base_url: str = PRACTICE_BASE_URL,
) -> dict[str, dict]:
    """Live bid/ask/mid pricing for one or more pairs, keyed by OANDA
    instrument name (e.g. "EUR_USD")."""
    instruments = ",".join(pips.normalize(p) for p in pairs)
    cache_key = f"pricing:{instruments}:{base_url}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    data = _request(
        "GET",
        f"/accounts/{account_id}/pricing",
        token,
        base_url,
        params={"instruments": instruments},
    )
    out: dict[str, dict] = {}
    for p in data.get("prices", []):
        instrument = p.get("instrument")
        bids = p.get("bids") or [{}]
        asks = p.get("asks") or [{}]
        bid = float(bids[0]["price"]) if bids and bids[0].get("price") else None
        ask = float(asks[0]["price"]) if asks and asks[0].get("price") else None
        mid = (bid + ask) / 2 if bid is not None and ask is not None else None
        spread_pips = pips.to_pips(instrument, ask - bid) if bid is not None and ask is not None else None
        out[instrument] = {
            "instrument": instrument,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread_pips": round(spread_pips, 1) if spread_pips is not None else None,
            "tradeable": p.get("tradeable", True),
            "time": p.get("time"),
        }
    cache.set(cache_key, out, PRICING_TTL)
    return out


# --- Account & trading --------------------------------------------------------


def get_account_summary(token: str, account_id: str, base_url: str = PRACTICE_BASE_URL) -> dict:
    data = _request("GET", f"/accounts/{account_id}/summary", token, base_url)
    return data.get("account", {})


def get_open_positions(token: str, account_id: str, base_url: str = PRACTICE_BASE_URL) -> list[dict]:
    data = _request("GET", f"/accounts/{account_id}/openPositions", token, base_url)
    return data.get("positions", [])


def get_open_trades(token: str, account_id: str, base_url: str = PRACTICE_BASE_URL) -> list[dict]:
    data = _request("GET", f"/accounts/{account_id}/openTrades", token, base_url)
    return data.get("trades", [])


def place_market_order(
    token: str,
    account_id: str,
    pair: str,
    units: float,
    base_url: str = PRACTICE_BASE_URL,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
) -> dict:
    """Submit a market order. Positive `units` = long, negative = short.

    `base_url` decides whether this is a virtual fxPractice order or a REAL
    fxTrade order. Optional `stop_loss_price` / `take_profit_price` attach
    bracket orders on the fill.
    """
    instrument = pips.normalize(pair)
    decimals = pips.price_decimals(instrument)
    order: dict = {
        "type": "MARKET",
        "instrument": instrument,
        "units": str(int(units)),
        "timeInForce": "FOK",
        "positionFill": "DEFAULT",
    }
    if stop_loss_price is not None:
        order["stopLossOnFill"] = {"price": f"{stop_loss_price:.{decimals}f}", "timeInForce": "GTC"}
    if take_profit_price is not None:
        order["takeProfitOnFill"] = {"price": f"{take_profit_price:.{decimals}f}", "timeInForce": "GTC"}

    return _request(
        "POST",
        f"/accounts/{account_id}/orders",
        token,
        base_url,
        json={"order": order},
    )


def update_trade_stop_loss(
    token: str,
    account_id: str,
    trade_id: str,
    stop_loss_price: float,
    pair: str,
    base_url: str = PRACTICE_BASE_URL,
) -> dict:
    """Move the stop-loss on an existing open trade (e.g., to break-even)."""
    decimals = pips.price_decimals(pair)
    return _request(
        "PUT",
        f"/accounts/{account_id}/trades/{trade_id}/orders",
        token,
        base_url,
        json={
            "stopLoss": {
                "price": f"{stop_loss_price:.{decimals}f}",
                "timeInForce": "GTC",
            }
        },
    )


def close_trade(token: str, account_id: str, trade_id: str, base_url: str = PRACTICE_BASE_URL) -> dict:
    """Fully close a single open trade by its OANDA trade ID."""
    return _request(
        "PUT",
        f"/accounts/{account_id}/trades/{trade_id}/close",
        token,
        base_url,
        json={"units": "ALL"},
    )


def close_position(
    token: str,
    account_id: str,
    pair: str,
    side: str,
    base_url: str = PRACTICE_BASE_URL,
) -> dict:
    """Close the entire long or short position on a pair. `side` is
    "long" or "short"."""
    instrument = pips.normalize(pair)
    body = {"longUnits": "ALL"} if side == "long" else {"shortUnits": "ALL"}
    return _request(
        "PUT",
        f"/accounts/{account_id}/positions/{instrument}/close",
        token,
        base_url,
        json=body,
    )
