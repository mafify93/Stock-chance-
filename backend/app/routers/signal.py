from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from .. import models
from ..ml.model import ml_predictor
from ..providers import yahoo
from ..signals import analyze

router = APIRouter(prefix="/api", tags=["signal"])


@router.get("/signal/{symbol}", response_model=models.SignalResponse)
async def signal(symbol: str, include_analyst: bool = Query(True, description="Include free analyst price-target data when available")):
    """Composite buy/sell/hold technical signal with full reasoning.

    Combines trend (SMA 50/200, golden/death cross), momentum (RSI, MACD,
    Stochastic), volatility (Bollinger Bands, ATR) and volume into a single
    score from -1 (strong sell) to +1 (strong buy), plus suggested entry/
    stop-loss/take-profit levels derived from ATR.
    """
    symbol = symbol.upper()
    try:
        df = await run_in_threadpool(yahoo.get_history, symbol, "1y", "1d")
        result = await run_in_threadpool(analyze, symbol, df)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Signal computation failed: {exc}") from exc

    analyst = None
    if include_analyst:
        try:
            analyst_data = await run_in_threadpool(yahoo.get_analyst_outlook, symbol)
            analyst = models.AnalystOutlook(**analyst_data)
        except Exception:  # noqa: BLE001
            analyst = None

    ml_result = await run_in_threadpool(ml_predictor.predict, df)

    return models.SignalResponse(
        symbol=result.symbol,
        action=result.action,
        score=result.score,
        confidence=result.confidence,
        price=result.price,
        reasons=result.reasons,
        indicators=result.indicators,
        levels=result.levels,
        analyst=analyst,
        ml=models.MLPrediction(**ml_result) if ml_result else None,
    )
