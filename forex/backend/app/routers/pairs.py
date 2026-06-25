from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from .. import models, pips
from ..providers import oanda
from ..universe import MAJORS, MINORS
from . import deps

router = APIRouter(prefix="/api", tags=["pairs"])


def _pair_info(pair: str, category: str) -> models.PairInfo:
    return models.PairInfo(
        pair=pair,
        display=pips.display(pair),
        base=pips.base_currency(pair),
        quote=pips.quote_currency(pair),
        pip_size=pips.pip_size(pair),
        category=category,
    )


@router.get("/pairs", response_model=list[models.PairInfo])
async def list_pairs(
    q: str | None = Query(None, description="Optional filter on pair name, e.g. 'eur' or 'jpy'")
):
    """The tradable currency-pair universe (majors + popular crosses)."""
    items = [_pair_info(p, "major") for p in MAJORS] + [_pair_info(p, "minor") for p in MINORS]
    if q:
        needle = q.upper().replace("/", "").replace("_", "")
        items = [i for i in items if needle in i.pair.replace("_", "")]
    return items


@router.get("/quote/{pair}", response_model=models.PairQuote)
async def quote(
    pair: str,
    oanda_api_token: str | None = Header(None, alias="Oanda-Api-Token"),
    oanda_account_id: str | None = Header(None, alias="Oanda-Account-Id"),
    oanda_api_env: str | None = Header(None, alias="Oanda-Api-Env"),
):
    """Live bid/ask/mid and spread for one pair (requires OANDA credentials)."""
    token = deps.require_token(oanda_api_token)
    account_id = deps.require_account(oanda_account_id)
    url = deps.base_url(oanda_api_env)
    instrument = pips.normalize(pair)
    try:
        pricing = await run_in_threadpool(oanda.get_pricing, [instrument], token, account_id, url)
    except oanda.OandaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    p = pricing.get(instrument)
    if not p:
        raise HTTPException(status_code=404, detail=f"No pricing for {pips.display(pair)}")
    return models.PairQuote(pair=instrument, display=pips.display(instrument), **{
        k: p[k] for k in ("bid", "ask", "mid", "spread_pips", "tradeable", "time")
    })


@router.get("/candles/{pair}", response_model=list[models.Candle])
async def candles(
    pair: str,
    granularity: str = Query("H1", description="OANDA granularity: M5, M15, H1, H4, D, ..."),
    count: int = Query(300, ge=10, le=2000),
    token: str = Depends(deps.oanda_token),
    oanda_api_env: str | None = Header(None, alias="Oanda-Api-Env"),
):
    """OHLCV candles for charting and analysis."""
    url = deps.base_url(oanda_api_env)
    try:
        df = await run_in_threadpool(oanda.get_candles, pair, token, granularity, count, url)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except oanda.OandaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    decimals = pips.price_decimals(pair)
    return [
        models.Candle(
            date=idx.isoformat(),
            open=round(float(row.Open), decimals),
            high=round(float(row.High), decimals),
            low=round(float(row.Low), decimals),
            close=round(float(row.Close), decimals),
            volume=float(row.Volume),
        )
        for idx, row in df.iterrows()
    ]
