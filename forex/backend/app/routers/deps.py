"""Shared helpers for pulling OANDA credentials out of request headers.

The backend is stateless about credentials: the iOS app holds the user's
OANDA API token and account ID in its Keychain and sends them on every
request. Data endpoints (candles/pricing) need the token; trading endpoints
also need the account ID. `Oanda-Api-Env: practice|live` selects the
environment - defaulting to the safe practice (demo) environment.
"""
from __future__ import annotations

from fastapi import Header, HTTPException

from ..providers import oanda

_MISSING_TOKEN = (
    "Missing OANDA API token. Add your OANDA API token and account ID in "
    "Settings > Broker."
)
_MISSING_ACCOUNT = (
    "Missing OANDA account ID. Add it in Settings > Broker."
)
_INVALID_ENV = "Oanda-Api-Env must be 'practice' or 'live'"


def base_url(env: str | None) -> str:
    env = (env or "practice").lower()
    if env not in ("practice", "live"):
        raise HTTPException(status_code=400, detail=_INVALID_ENV)
    return oanda.LIVE_BASE_URL if env == "live" else oanda.PRACTICE_BASE_URL


def require_token(token: str | None) -> str:
    if not token:
        raise HTTPException(status_code=401, detail=_MISSING_TOKEN)
    return token


def require_account(account_id: str | None) -> str:
    if not account_id:
        raise HTTPException(status_code=401, detail=_MISSING_ACCOUNT)
    return account_id


def oanda_token(oanda_api_token: str | None = Header(None, alias="Oanda-Api-Token")) -> str:
    return require_token(oanda_api_token)
