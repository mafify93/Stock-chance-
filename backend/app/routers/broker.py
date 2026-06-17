from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from .. import models
from ..providers import alpaca, questrade

router = APIRouter(prefix="/api/broker", tags=["broker"])

_MISSING_CREDENTIALS = (
    "Missing Alpaca API credentials. Add your Alpaca API Key ID and Secret Key "
    "in Settings > Broker."
)

_INVALID_ENV = "Apca-Api-Env must be 'paper' or 'live'"

_QT_MISSING_TOKEN = (
    "Missing Questrade access token. Connect your Questrade account in "
    "Settings > Live Trading."
)


def _credentials(api_key_id: str | None, api_secret_key: str | None) -> tuple[str, str]:
    if not api_key_id or not api_secret_key:
        raise HTTPException(status_code=401, detail=_MISSING_CREDENTIALS)
    return api_key_id, api_secret_key


def _alpaca_base_url(env: str | None) -> str:
    env = (env or "paper").lower()
    if env not in ("paper", "live"):
        raise HTTPException(status_code=400, detail=_INVALID_ENV)
    return alpaca.LIVE_BASE_URL if env == "live" else alpaca.PAPER_BASE_URL


def _questrade_auth(access_token: str | None, api_server: str | None) -> tuple[str, str]:
    if not access_token or not api_server:
        raise HTTPException(status_code=401, detail=_QT_MISSING_TOKEN)
    return access_token, api_server


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# --- Alpaca (paper or live, selected via Apca-Api-Env) -----------------------


@router.get("/account", response_model=models.BrokerAccount)
async def account(
    apca_api_key_id: str | None = Header(None, alias="Apca-Api-Key-Id"),
    apca_api_secret_key: str | None = Header(None, alias="Apca-Api-Secret-Key"),
    apca_api_env: str | None = Header(None, alias="Apca-Api-Env"),
):
    """Alpaca account summary (buying power, equity, cash). `Apca-Api-Env:
    live` routes this to the user's REAL brokerage account."""
    key, secret = _credentials(apca_api_key_id, apca_api_secret_key)
    base_url = _alpaca_base_url(apca_api_env)
    try:
        data = await run_in_threadpool(alpaca.get_account, key, secret, base_url)
    except alpaca.AlpacaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return models.BrokerAccount(
        account_number=data.get("account_number"),
        status=data.get("status"),
        buying_power=_to_float(data.get("buying_power")),
        cash=_to_float(data.get("cash")),
        portfolio_value=_to_float(data.get("portfolio_value")),
        equity=_to_float(data.get("equity")),
        currency=data.get("currency"),
        pattern_day_trader=data.get("pattern_day_trader"),
        trading_blocked=data.get("trading_blocked"),
    )


@router.get("/positions", response_model=list[models.BrokerPosition])
async def positions(
    apca_api_key_id: str | None = Header(None, alias="Apca-Api-Key-Id"),
    apca_api_secret_key: str | None = Header(None, alias="Apca-Api-Secret-Key"),
    apca_api_env: str | None = Header(None, alias="Apca-Api-Env"),
):
    """Currently-held Alpaca positions. `Apca-Api-Env: live` routes this to
    the user's REAL brokerage account."""
    key, secret = _credentials(apca_api_key_id, apca_api_secret_key)
    base_url = _alpaca_base_url(apca_api_env)
    try:
        data = await run_in_threadpool(alpaca.get_positions, key, secret, base_url)
    except alpaca.AlpacaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return [
        models.BrokerPosition(
            symbol=p.get("symbol"),
            quantity=_to_float(p.get("qty")) or 0.0,
            avg_entry_price=_to_float(p.get("avg_entry_price")) or 0.0,
            current_price=_to_float(p.get("current_price")),
            market_value=_to_float(p.get("market_value")),
            unrealized_pl=_to_float(p.get("unrealized_pl")),
            unrealized_plpc=_to_float(p.get("unrealized_plpc")),
        )
        for p in data
    ]


@router.post("/order", response_model=models.BrokerOrder)
async def place_order(
    order: models.BrokerOrderRequest,
    apca_api_key_id: str | None = Header(None, alias="Apca-Api-Key-Id"),
    apca_api_secret_key: str | None = Header(None, alias="Apca-Api-Secret-Key"),
    apca_api_env: str | None = Header(None, alias="Apca-Api-Env"),
):
    """Submit a market order to Alpaca.

    `Apca-Api-Env: paper` (the default) routes to Alpaca's simulated paper
    account - no real money at risk. `Apca-Api-Env: live` routes to the
    user's REAL brokerage account and places a REAL order with REAL money.
    The backend trusts the caller (the iOS app) to have obtained explicit
    user confirmation before sending a live order.
    """
    key, secret = _credentials(apca_api_key_id, apca_api_secret_key)
    base_url = _alpaca_base_url(apca_api_env)
    if order.side not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="side must be 'buy' or 'sell'")
    if order.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be greater than 0")

    try:
        data = await run_in_threadpool(
            alpaca.place_order,
            key,
            secret,
            order.symbol,
            order.quantity,
            order.side,
            order.type,
            order.time_in_force,
            base_url,
        )
    except alpaca.AlpacaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return models.BrokerOrder(
        id=data.get("id", ""),
        symbol=data.get("symbol"),
        quantity=_to_float(data.get("qty")),
        side=data.get("side"),
        type=data.get("type"),
        status=data.get("status"),
        submitted_at=data.get("submitted_at"),
        filled_avg_price=_to_float(data.get("filled_avg_price")),
    )


# --- Questrade (LIVE, real money only) ----------------------------------------


@router.post("/questrade/token", response_model=models.QuestradeAuthResponse)
async def questrade_token(body: models.QuestradeTokenRequest):
    """Exchange a Questrade refresh token for a fresh access token.

    Questrade rotates refresh tokens on every use - the response's
    `refresh_token` must be persisted by the caller (replacing the one that
    was just sent) or the next refresh will fail.
    """
    try:
        data = await run_in_threadpool(questrade.refresh_access_token, body.refresh_token)
    except questrade.QuestradeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return models.QuestradeAuthResponse(
        access_token=data["access_token"],
        api_server=data["api_server"],
        refresh_token=data["refresh_token"],
        expires_in=data["expires_in"],
        token_type=data.get("token_type", "Bearer"),
    )


@router.get("/questrade/accounts", response_model=list[models.QuestradeAccount])
async def questrade_accounts(
    questrade_access_token: str | None = Header(None, alias="Questrade-Access-Token"),
    questrade_api_server: str | None = Header(None, alias="Questrade-Api-Server"),
):
    """The user's Questrade accounts (real brokerage accounts)."""
    token, server = _questrade_auth(questrade_access_token, questrade_api_server)
    try:
        data = await run_in_threadpool(questrade.get_accounts, token, server)
    except questrade.QuestradeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return [
        models.QuestradeAccount(
            account_number=a.get("number"),
            type=a.get("type"),
            status=a.get("status"),
            is_primary=a.get("isPrimary"),
        )
        for a in data
    ]


@router.get("/questrade/balances", response_model=models.QuestradeBalances)
async def questrade_balances(
    account_number: str = Query(..., description="Questrade account number"),
    questrade_access_token: str | None = Header(None, alias="Questrade-Access-Token"),
    questrade_api_server: str | None = Header(None, alias="Questrade-Api-Server"),
):
    token, server = _questrade_auth(questrade_access_token, questrade_api_server)
    try:
        data = await run_in_threadpool(questrade.get_balances, token, server, account_number)
    except questrade.QuestradeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    combined = (data.get("combinedBalances") or [{}])[0]
    return models.QuestradeBalances(
        currency=combined.get("currency"),
        cash=_to_float(combined.get("cash")),
        market_value=_to_float(combined.get("marketValue")),
        total_equity=_to_float(combined.get("totalEquity")),
        buying_power=_to_float(combined.get("buyingPower")),
    )


@router.get("/questrade/positions", response_model=list[models.QuestradePosition])
async def questrade_positions(
    account_number: str = Query(..., description="Questrade account number"),
    questrade_access_token: str | None = Header(None, alias="Questrade-Access-Token"),
    questrade_api_server: str | None = Header(None, alias="Questrade-Api-Server"),
):
    token, server = _questrade_auth(questrade_access_token, questrade_api_server)
    try:
        data = await run_in_threadpool(questrade.get_positions, token, server, account_number)
    except questrade.QuestradeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return [
        models.QuestradePosition(
            symbol=p.get("symbol"),
            quantity=_to_float(p.get("openQuantity")) or 0.0,
            avg_entry_price=_to_float(p.get("averageEntryPrice")) or 0.0,
            current_price=_to_float(p.get("currentPrice")),
            market_value=_to_float(p.get("currentMarketValue")),
            unrealized_pl=_to_float(p.get("openPnl")),
        )
        for p in data
    ]


@router.get("/questrade/symbols", response_model=list[models.QuestradeSymbol])
async def questrade_symbols(
    q: str = Query(..., min_length=1, description="Ticker or company name prefix to search for"),
    questrade_access_token: str | None = Header(None, alias="Questrade-Access-Token"),
    questrade_api_server: str | None = Header(None, alias="Questrade-Api-Server"),
):
    """Look up Questrade's internal `symbolId` for a ticker - required to
    place an order."""
    token, server = _questrade_auth(questrade_access_token, questrade_api_server)
    try:
        data = await run_in_threadpool(questrade.search_symbols, token, server, q)
    except questrade.QuestradeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return [
        models.QuestradeSymbol(
            symbol=s.get("symbol"),
            symbol_id=s.get("symbolId"),
            description=s.get("description"),
        )
        for s in data
    ]


@router.post("/questrade/order", response_model=models.QuestradeOrder)
async def questrade_order(
    order: models.QuestradeOrderRequest,
    questrade_access_token: str | None = Header(None, alias="Questrade-Access-Token"),
    questrade_api_server: str | None = Header(None, alias="Questrade-Api-Server"),
):
    """Submit a REAL order to the user's live Questrade account. `side` must
    be "Buy" or "Sell". The backend trusts the caller (the iOS app) to have
    obtained explicit user confirmation before sending this."""
    token, server = _questrade_auth(questrade_access_token, questrade_api_server)
    if order.side not in ("Buy", "Sell"):
        raise HTTPException(status_code=400, detail="side must be 'Buy' or 'Sell'")
    if order.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be greater than 0")

    try:
        data = await run_in_threadpool(
            questrade.place_order,
            token,
            server,
            order.account_number,
            order.symbol_id,
            order.quantity,
            order.side,
            order.order_type,
            order.time_in_force,
            order.limit_price,
        )
    except questrade.QuestradeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    placed = (data.get("orders") or [{}])[0]
    return models.QuestradeOrder(
        id=placed.get("id", 0),
        symbol=order.symbol,
        quantity=_to_float(placed.get("quantity")) or order.quantity,
        side=placed.get("side") or order.side,
        type=placed.get("type") or order.order_type,
        state=placed.get("state"),
        avg_exec_price=_to_float(placed.get("avgExecPrice")),
    )
