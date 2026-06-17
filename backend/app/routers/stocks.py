from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from .. import models
from ..providers import yahoo

router = APIRouter(prefix="/api", tags=["stocks"])


@router.get("/search", response_model=list[models.SearchResult])
async def search(q: str = Query(..., min_length=1), limit: int = 10):
    """Search for any stock, ETF, index, crypto or FX symbol by name or ticker."""
    try:
        results = await run_in_threadpool(yahoo.search_symbols, q, limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Search failed: {exc}") from exc
    return results


@router.get("/quote/{symbol}", response_model=models.Quote)
async def quote(symbol: str):
    """Near real-time price snapshot for a symbol."""
    try:
        data = await run_in_threadpool(yahoo.get_quote, symbol)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Quote lookup failed: {exc}") from exc
    return data


@router.get("/history/{symbol}", response_model=list[models.Candle])
async def history(symbol: str, period: str = "6mo", interval: str = "1d"):
    """OHLCV candles for charting.

    `period` examples: 1d, 5d, 1mo, 6mo, 1y, 2y, 5y, max
    `interval` examples: 1m, 5m, 15m, 1h, 1d, 1wk, 1mo
    """
    try:
        df = await run_in_threadpool(yahoo.get_history, symbol, period, interval)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"History lookup failed: {exc}") from exc

    candles = [
        models.Candle(
            date=idx.isoformat(),
            open=round(float(row.Open), 4),
            high=round(float(row.High), 4),
            low=round(float(row.Low), 4),
            close=round(float(row.Close), 4),
            volume=float(row.Volume),
        )
        for idx, row in df.iterrows()
    ]
    return candles
