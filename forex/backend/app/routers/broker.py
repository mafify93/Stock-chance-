from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.concurrency import run_in_threadpool

from .. import models, pips
from ..providers import oanda
from . import deps

router = APIRouter(prefix="/api/broker", tags=["broker"])


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _creds(token: str | None, account_id: str | None, env: str | None) -> tuple[str, str, str]:
    return deps.require_token(token), deps.require_account(account_id), deps.base_url(env)


@router.get("/account", response_model=models.BrokerAccount)
async def account(
    oanda_api_token: str | None = Header(None, alias="Oanda-Api-Token"),
    oanda_account_id: str | None = Header(None, alias="Oanda-Account-Id"),
    oanda_api_env: str | None = Header(None, alias="Oanda-Api-Env"),
):
    """OANDA account summary (balance, NAV, margin, open P/L). `Oanda-Api-Env:
    live` routes this to the user's REAL fxTrade account."""
    token, account_id, url = _creds(oanda_api_token, oanda_account_id, oanda_api_env)
    try:
        data = await run_in_threadpool(oanda.get_account_summary, token, account_id, url)
    except oanda.OandaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return models.BrokerAccount(
        account_id=data.get("id"),
        alias=data.get("alias"),
        currency=data.get("currency"),
        balance=_to_float(data.get("balance")),
        nav=_to_float(data.get("NAV")),
        unrealized_pl=_to_float(data.get("unrealizedPL")),
        realized_pl=_to_float(data.get("pl")),
        margin_used=_to_float(data.get("marginUsed")),
        margin_available=_to_float(data.get("marginAvailable")),
        open_trade_count=data.get("openTradeCount"),
        open_position_count=data.get("openPositionCount"),
    )


@router.get("/positions", response_model=list[models.BrokerPosition])
async def positions(
    oanda_api_token: str | None = Header(None, alias="Oanda-Api-Token"),
    oanda_account_id: str | None = Header(None, alias="Oanda-Account-Id"),
    oanda_api_env: str | None = Header(None, alias="Oanda-Api-Env"),
):
    """Currently-open OANDA positions, split into long/short sides with
    unrealized P/L (in account currency and in pips)."""
    token, account_id, url = _creds(oanda_api_token, oanda_account_id, oanda_api_env)
    try:
        raw = await run_in_threadpool(oanda.get_open_positions, token, account_id, url)
    except oanda.OandaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    out: list[models.BrokerPosition] = []
    for p in raw:
        instrument = p.get("instrument")
        for side in ("long", "short"):
            leg = p.get(side) or {}
            units = _to_float(leg.get("units")) or 0.0
            if units == 0:
                continue
            avg_price = _to_float(leg.get("averagePrice")) or 0.0
            unrealized = _to_float(leg.get("unrealizedPL"))
            out.append(
                models.BrokerPosition(
                    pair=instrument,
                    display=pips.display(instrument),
                    side=side,
                    units=abs(units),
                    avg_price=avg_price,
                    current_price=None,
                    unrealized_pl=unrealized,
                    pl_pips=None,
                )
            )
    return out


@router.post("/order", response_model=models.BrokerOrder)
async def place_order(
    order: models.BrokerOrderRequest,
    oanda_api_token: str | None = Header(None, alias="Oanda-Api-Token"),
    oanda_account_id: str | None = Header(None, alias="Oanda-Account-Id"),
    oanda_api_env: str | None = Header(None, alias="Oanda-Api-Env"),
):
    """Submit a market order to OANDA. Positive `units` go long, negative go
    short.

    `Oanda-Api-Env: practice` (the default) routes to the fxPractice demo
    account - virtual money. `Oanda-Api-Env: live` routes to the user's REAL
    fxTrade account and places a REAL order with REAL money. The backend
    trusts the caller (the iOS app) to have obtained explicit user
    confirmation before sending a live order.
    """
    token, account_id, url = _creds(oanda_api_token, oanda_account_id, oanda_api_env)
    if order.units == 0:
        raise HTTPException(status_code=400, detail="units must be non-zero (positive = buy, negative = sell)")

    try:
        data = await run_in_threadpool(
            oanda.place_market_order,
            token,
            account_id,
            order.pair,
            order.units,
            url,
            order.stop_loss_price,
            order.take_profit_price,
        )
    except oanda.OandaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    instrument = pips.normalize(order.pair)
    fill = data.get("orderFillTransaction")
    if fill:
        filled_units = _to_float(fill.get("units"))
        return models.BrokerOrder(
            id=fill.get("id"),
            pair=instrument,
            display=pips.display(instrument),
            units=filled_units,
            side="buy" if (filled_units or 0) > 0 else "sell",
            status="FILLED",
            fill_price=_to_float(fill.get("price")),
            time=fill.get("time"),
            reason=fill.get("reason"),
        )

    # No fill - usually cancelled (e.g. market closed, insufficient margin).
    cancel = data.get("orderCancelTransaction") or {}
    return models.BrokerOrder(
        id=cancel.get("id"),
        pair=instrument,
        display=pips.display(instrument),
        units=order.units,
        side="buy" if order.units > 0 else "sell",
        status="CANCELLED",
        reason=cancel.get("reason", "Order was not filled"),
    )


@router.post("/close", response_model=models.CloseResponse)
async def close(
    body: models.CloseRequest,
    oanda_api_token: str | None = Header(None, alias="Oanda-Api-Token"),
    oanda_account_id: str | None = Header(None, alias="Oanda-Account-Id"),
    oanda_api_env: str | None = Header(None, alias="Oanda-Api-Env"),
):
    """Close the entire long or short position on a pair."""
    token, account_id, url = _creds(oanda_api_token, oanda_account_id, oanda_api_env)
    if body.side not in ("long", "short"):
        raise HTTPException(status_code=400, detail="side must be 'long' or 'short'")

    instrument = pips.normalize(body.pair)
    try:
        data = await run_in_threadpool(oanda.close_position, token, account_id, instrument, body.side, url)
    except oanda.OandaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    fill_key = "longOrderFillTransaction" if body.side == "long" else "shortOrderFillTransaction"
    fill = data.get(fill_key) or {}
    realized = _to_float(fill.get("pl"))
    return models.CloseResponse(
        pair=instrument,
        display=pips.display(instrument),
        closed=bool(fill),
        realized_pl=realized,
        message=(
            f"Closed {pips.display(instrument)} {body.side} position"
            + (f" for {realized:+.2f} realized P/L" if realized is not None else "")
            if fill
            else f"No open {body.side} position found for {pips.display(instrument)}"
        ),
    )
