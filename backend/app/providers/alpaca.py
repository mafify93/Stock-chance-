"""Thin client for Alpaca's trading REST API (paper AND live).

This backend never stores brokerage credentials: the iOS app keeps the
user's Alpaca API key/secret in its Keychain and sends them on each request
via the `Apca-Api-Key-Id` / `Apca-Api-Secret-Key` headers (plus an
`Apca-Api-Env: paper|live` header to pick which account to hit), which this
module forwards directly to Alpaca.

`PAPER_BASE_URL` talks to Alpaca's simulated paper-trading account - no real
money at risk. `LIVE_BASE_URL` talks to the user's real brokerage account and
places REAL orders with REAL money - the iOS app gates this behind an
explicit "Live Trading" acknowledgment and a per-order confirmation, since
this backend has no way to know what the user intends beyond what they send.
"""
from __future__ import annotations

import httpx

PAPER_BASE_URL = "https://paper-api.alpaca.markets/v2"
LIVE_BASE_URL = "https://api.alpaca.markets/v2"


class AlpacaError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


def _headers(api_key: str, api_secret: str) -> dict:
    return {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }


def _request(method: str, path: str, api_key: str, api_secret: str, base_url: str, **kwargs) -> dict | list:
    url = f"{base_url}{path}"
    try:
        resp = httpx.request(method, url, headers=_headers(api_key, api_secret), timeout=15, **kwargs)
    except httpx.HTTPError as exc:
        raise AlpacaError(502, f"Could not reach Alpaca: {exc}") from exc

    if resp.status_code >= 400:
        detail = resp.text
        try:
            detail = resp.json().get("message", detail)
        except Exception:  # noqa: BLE001
            pass
        raise AlpacaError(resp.status_code, detail)

    if not resp.content:
        return {}
    return resp.json()


def get_account(api_key: str, api_secret: str, base_url: str = PAPER_BASE_URL) -> dict:
    """Account summary (buying power, equity, cash, status)."""
    return _request("GET", "/account", api_key, api_secret, base_url)


def get_positions(api_key: str, api_secret: str, base_url: str = PAPER_BASE_URL) -> list[dict]:
    """Currently-held positions."""
    return _request("GET", "/positions", api_key, api_secret, base_url)


def place_order(
    api_key: str,
    api_secret: str,
    symbol: str,
    qty: float,
    side: str,
    order_type: str = "market",
    time_in_force: str = "day",
    base_url: str = PAPER_BASE_URL,
) -> dict:
    """Submit an order. `base_url` determines whether this is a simulated
    paper-trading order or a REAL order against the user's live account."""
    payload = {
        "symbol": symbol.upper(),
        "qty": str(qty),
        "side": side,
        "type": order_type,
        "time_in_force": time_in_force,
    }
    return _request("POST", "/orders", api_key, api_secret, base_url, json=payload)
