from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.concurrency import run_in_threadpool

from .. import models
from ..providers import alpaca

router = APIRouter(prefix="/api/broker", tags=["broker"])

_MISSING_CREDENTIALS = (
    "Missing Alpaca paper-trading API credentials. Add your Alpaca API Key ID "
    "and Secret Key in Settings > Broker (Paper Trading)."
)


def _credentials(api_key_id: str | None, api_secret_key: str | None) -> tuple[str, str]:
    if not api_key_id or not api_secret_key:
        raise HTTPException(status_code=401, detail=_MISSING_CREDENTIALS)
    return api_key_id, api_secret_key


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@router.get("/account", response_model=models.BrokerAccount)
async def account(
    apca_api_key_id: str | None = Header(None, alias="Apca-Api-Key-Id"),
    apca_api_secret_key: str | None = Header(None, alias="Apca-Api-Secret-Key"),
):
    """Alpaca paper-trading account summary (buying power, equity, cash)."""
    key, secret = _credentials(apca_api_key_id, apca_api_secret_key)
    try:
        data = await run_in_threadpool(alpaca.get_account, key, secret)
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
):
    """Currently-held Alpaca paper-trading positions."""
    key, secret = _credentials(apca_api_key_id, apca_api_secret_key)
    try:
        data = await run_in_threadpool(alpaca.get_positions, key, secret)
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
):
    """Submit a market order to Alpaca's **paper trading** account.

    Always routed to Alpaca's paper-trading endpoint - no real money is at
    risk. This lets the app's Buy/Sell flow be exercised end-to-end safely.
    """
    key, secret = _credentials(apca_api_key_id, apca_api_secret_key)
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
