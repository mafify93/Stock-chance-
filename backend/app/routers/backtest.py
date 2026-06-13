from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from .. import models
from ..backtest import run_backtest
from ..providers import yahoo

router = APIRouter(prefix="/api", tags=["backtest"])


@router.get("/backtest/{symbol}", response_model=models.BacktestResponse)
async def backtest(
    symbol: str,
    period: str = Query("2y", description="History window to backtest, e.g. 1y, 2y, 5y"),
    initial_capital: float = Query(10000.0, gt=0),
):
    """Simulate Stock Chance's signal engine against historical data.

    Walks forward day by day: buys when the signal turns Buy/Strong Buy
    while flat, sells when it turns Sell/Strong Sell while holding. Compares
    the resulting return to a simple buy-and-hold over the same period.
    """
    symbol = symbol.upper()
    try:
        df = await run_in_threadpool(yahoo.get_history, symbol, period, "1d")
        result = await run_in_threadpool(run_backtest, symbol, df, initial_capital)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Backtest failed: {exc}") from exc

    return models.BacktestResponse(**result)
