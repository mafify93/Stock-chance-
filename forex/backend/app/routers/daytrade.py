from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from .. import models, pips
from ..intraday import compute_day_signal
from ..providers import oanda
from ..sessions import get_market_session
from ..signals import analyze
from ..top_pick import evaluate_opportunity
from ..universe import DAYTRADE_UNIVERSE
from . import deps

router = APIRouter(prefix="/api/daytrade", tags=["daytrade"])

_CONCURRENCY = 6


@router.get("/session", response_model=models.MarketSessionResponse)
async def session():
    """The current forex trading clock: which regional sessions are live and
    whether the high-liquidity London/New York overlap is active."""
    return dataclasses.asdict(get_market_session())


@router.get("/signal/{pair}", response_model=models.DaySignalResponse)
async def day_signal(
    pair: str,
    token: str = Depends(deps.oanda_token),
    oanda_api_env: str | None = Header(None, alias="Oanda-Api-Env"),
):
    """Same-day Buy/Sell/Hold signal from recent 5-minute price action.

    VWAP position, opening-range breakout, short-term EMA momentum, intraday
    RSI dips/peaks and tick-volume spikes - plus a suggested target/stop in
    pips.
    """
    url = deps.base_url(oanda_api_env)
    instrument = pips.normalize(pair)
    try:
        df = await run_in_threadpool(oanda.get_candles, pair, token, "M5", 300, url)
        result = await run_in_threadpool(compute_day_signal, instrument, df)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except oanda.OandaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    data = dataclasses.asdict(result)
    data["display"] = pips.display(instrument)
    return data


@router.get("/intraday/{pair}", response_model=list[models.Candle])
async def intraday_history(
    pair: str,
    granularity: str = Query("M5", description="Intraday granularity (M1, M5, M15)"),
    count: int = Query(300, ge=10, le=1000),
    token: str = Depends(deps.oanda_token),
    oanda_api_env: str | None = Header(None, alias="Oanda-Api-Env"),
):
    """Intraday candles for charting today's session."""
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


@router.get("/top-pick", response_model=models.TopPickResponse)
async def top_pick(
    pairs: str | None = Query(
        None,
        description="Comma-separated pairs to scan. Defaults to the most liquid day-trading pairs.",
    ),
    count: int = Query(3, ge=1, le=10, description="How many ranked ideas to return"),
    token: str = Depends(deps.oanda_token),
    oanda_api_env: str | None = Header(None, alias="Oanda-Api-Env"),
):
    """The best (and next-best) trade ideas right now.

    Blends each pair's higher-timeframe trend with today's intraday momentum
    into one ranked "what to do right now" idea, then returns the top picks.
    """
    url = deps.base_url(oanda_api_env)
    pair_list = (
        [pips.normalize(p) for p in pairs.split(",") if p.strip()]
        if pairs
        else DAYTRADE_UNIVERSE
    )

    sem = asyncio.Semaphore(_CONCURRENCY)
    opportunities: list[models.Opportunity] = []
    errors: dict[str, str] = {}

    async def process(pair: str) -> None:
        async with sem:
            try:
                htf = await run_in_threadpool(oanda.get_candles, pair, token, "H1", 400, url)
                swing = await run_in_threadpool(analyze, pair, htf)

                day = None
                try:
                    m5 = await run_in_threadpool(oanda.get_candles, pair, token, "M5", 300, url)
                    day = await run_in_threadpool(compute_day_signal, pair, m5)
                except Exception:  # noqa: BLE001 - intraday is best-effort
                    pass

                opp = evaluate_opportunity(pair, swing, day)
                opportunities.append(
                    models.Opportunity(display=pips.display(pair), **dataclasses.asdict(opp))
                )
            except Exception as exc:  # noqa: BLE001
                errors[pips.display(pair)] = str(exc)

    await asyncio.gather(*(process(p) for p in pair_list))

    ranked = sorted(opportunities, key=lambda o: o.opportunity_score, reverse=True)

    return models.TopPickResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        session=dataclasses.asdict(get_market_session()),
        picks=ranked[:count],
        errors=errors,
    )
