from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from .. import models, pips
from ..providers import oanda
from ..signals import analyze
from . import deps

router = APIRouter(prefix="/api", tags=["signal"])


@router.get("/signal/{pair}", response_model=models.SignalResponse)
async def signal(
    pair: str,
    granularity: str = Query("H1", description="Timeframe for the swing signal: H1, H4, D"),
    token: str = Depends(deps.oanda_token),
    oanda_api_env: str | None = Header(None, alias="Oanda-Api-Env"),
):
    """Composite buy/sell/hold technical signal with full reasoning.

    Combines trend (SMA 50/200, golden/death cross), momentum (RSI, MACD,
    Stochastic), volatility (Bollinger Bands, ATR) and tick volume into a
    single score from -1 (strong sell) to +1 (strong buy), plus suggested
    entry / stop-loss / take-profit levels (in pips) derived from ATR.
    """
    url = deps.base_url(oanda_api_env)
    try:
        df = await run_in_threadpool(oanda.get_candles, pair, token, granularity, 400, url)
        result = await run_in_threadpool(analyze, pips.normalize(pair), df)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except oanda.OandaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Signal computation failed: {exc}") from exc

    return models.SignalResponse(
        pair=result.pair,
        display=pips.display(result.pair),
        action=result.action,
        score=result.score,
        confidence=result.confidence,
        price=result.price,
        reasons=result.reasons,
        indicators=result.indicators,
        levels=result.levels,
    )
