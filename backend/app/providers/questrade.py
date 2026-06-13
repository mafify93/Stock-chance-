"""Thin client for Questrade's REST API - a Canadian brokerage.

**This talks to the user's real, live Questrade account. Orders placed
through this module use real money.**

Questrade uses OAuth2 refresh tokens issued from the "App Hub" in a user's
Questrade account. Refresh tokens are single-use: exchanging one for an
access token returns a *new* refresh token, and the old one is immediately
invalidated. The backend never stores these tokens - it forwards the token
the iOS app sends and returns whatever Questrade issues back, and the app is
responsible for persisting the rotated refresh token in its Keychain.
"""
from __future__ import annotations

import httpx

AUTH_URL = "https://login.questrade.com/oauth2/token"


class QuestradeError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


def refresh_access_token(refresh_token: str) -> dict:
    """Exchange a refresh token for a fresh access token + API server +
    rotated refresh token."""
    try:
        resp = httpx.get(
            AUTH_URL,
            params={"grant_type": "refresh_token", "refresh_token": refresh_token},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise QuestradeError(502, f"Could not reach Questrade: {exc}") from exc

    if resp.status_code >= 400:
        raise QuestradeError(resp.status_code, "Questrade rejected this refresh token. Generate a new one from Questrade's App Hub and reconnect.")

    return resp.json()


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _request(method: str, api_server: str, path: str, access_token: str, **kwargs) -> dict:
    url = f"{api_server.rstrip('/')}{path}"
    try:
        resp = httpx.request(method, url, headers=_headers(access_token), timeout=15, **kwargs)
    except httpx.HTTPError as exc:
        raise QuestradeError(502, f"Could not reach Questrade: {exc}") from exc

    if resp.status_code >= 400:
        detail = resp.text
        try:
            detail = resp.json().get("message", detail)
        except Exception:  # noqa: BLE001
            pass
        raise QuestradeError(resp.status_code, detail)

    if not resp.content:
        return {}
    return resp.json()


def get_accounts(access_token: str, api_server: str) -> list[dict]:
    data = _request("GET", api_server, "/v1/accounts", access_token)
    return data.get("accounts", [])


def get_balances(access_token: str, api_server: str, account_number: str) -> dict:
    return _request("GET", api_server, f"/v1/accounts/{account_number}/balances", access_token)


def get_positions(access_token: str, api_server: str, account_number: str) -> list[dict]:
    data = _request("GET", api_server, f"/v1/accounts/{account_number}/positions", access_token)
    return data.get("positions", [])


def search_symbols(access_token: str, api_server: str, prefix: str) -> list[dict]:
    data = _request("GET", api_server, "/v1/symbols/search", access_token, params={"prefix": prefix})
    return data.get("symbols", [])


def place_order(
    access_token: str,
    api_server: str,
    account_number: str,
    symbol_id: int,
    quantity: float,
    side: str,
    order_type: str = "Market",
    time_in_force: str = "Day",
    limit_price: float | None = None,
) -> dict:
    """Submit a REAL order to the user's live Questrade account. `side` must
    be "Buy" or "Sell"."""
    payload = {
        "symbolId": symbol_id,
        "quantity": quantity,
        "icebergQuantity": None,
        "limitPrice": limit_price,
        "stopPrice": None,
        "isAllOrNone": False,
        "isAnonymous": False,
        "orderType": order_type,
        "timeInForce": time_in_force,
        "action": side,
        "primaryRoute": "AUTO",
        "secondaryRoute": "AUTO",
    }
    return _request("POST", api_server, f"/v1/accounts/{account_number}/orders", access_token, json=payload)
