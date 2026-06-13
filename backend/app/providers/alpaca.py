"""Thin client for Alpaca's paper-trading REST API.

This backend never stores brokerage credentials: the iOS app keeps the
user's Alpaca API key/secret in its Keychain and sends them on each request
via the `Apca-Api-Key-Id` / `Apca-Api-Secret-Key` headers, which this module
forwards directly to Alpaca.

Only the **paper trading** endpoint is used - see
https://alpaca.markets/docs/trading/paper-trading/. This is intentional:
paper trading lets the app place "real" orders against a simulated account
with no real money at risk, which is the safest way to validate the
Sell/Hold coach and order flow before ever considering live trading.
"""
from __future__ import annotations

import httpx

PAPER_BASE_URL = "https://paper-api.alpaca.markets/v2"


class AlpacaError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


def _headers(api_key: str, api_secret: str) -> dict:
    return {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }


def _request(method: str, path: str, api_key: str, api_secret: str, **kwargs) -> dict | list:
    url = f"{PAPER_BASE_URL}{path}"
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


def get_account(api_key: str, api_secret: str) -> dict:
    """Paper-trading account summary (buying power, equity, cash, status)."""
    return _request("GET", "/account", api_key, api_secret)


def get_positions(api_key: str, api_secret: str) -> list[dict]:
    """Currently-held paper-trading positions."""
    return _request("GET", "/positions", api_key, api_secret)


def place_order(
    api_key: str,
    api_secret: str,
    symbol: str,
    qty: float,
    side: str,
    order_type: str = "market",
    time_in_force: str = "day",
) -> dict:
    """Submit a paper-trading order."""
    payload = {
        "symbol": symbol.upper(),
        "qty": str(qty),
        "side": side,
        "type": order_type,
        "time_in_force": time_in_force,
    }
    return _request("POST", "/orders", api_key, api_secret, json=payload)
