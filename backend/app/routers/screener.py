from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from .. import models
from ..providers import yahoo
from ..signals import analyze
from ..universe import DEFAULT_UNIVERSE

router = APIRouter(prefix="/api", tags=["screener"])

_CONCURRENCY = 8


@router.get("/screener", response_model=models.ScreenerResponse)
async def screener(
    symbols: str | None = Query(
        None,
        description="Comma-separated list of symbols to scan. Defaults to a curated set of popular US stocks/ETFs.",
    ),
    top: int = Query(10, ge=1, le=50, description="Max number of results per bucket (buy/sell/hold)"),
):
    """Scan many symbols at once and rank them into Buy / Sell / Hold buckets.

    Answers "what should I buy/sell right now" by running the same signal
    engine as /api/signal across a whole watchlist (or the default
    curated universe) and sorting by confidence.
    """
    symbol_list = (
        [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if symbols
        else DEFAULT_UNIVERSE
    )

    sem = asyncio.Semaphore(_CONCURRENCY)
    results: list[models.ScreenerItem] = []
    errors: dict[str, str] = {}

    async def process(sym: str) -> None:
        async with sem:
            try:
                df = await run_in_threadpool(yahoo.get_history, sym, "6mo", "1d")
                result = await run_in_threadpool(analyze, sym, df)
                change_pct = None
                if len(df) > 1:
                    prev_close = float(df["Close"].iloc[-2])
                    if prev_close:
                        change_pct = round((result.price - prev_close) / prev_close * 100, 2)
                results.append(
                    models.ScreenerItem(
                        symbol=result.symbol,
                        action=result.action,
                        score=result.score,
                        confidence=result.confidence,
                        price=result.price,
                        change_percent=change_pct,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                errors[sym] = str(exc)

    await asyncio.gather(*(process(sym) for sym in symbol_list))

    buy = sorted(
        (r for r in results if r.action in ("BUY", "STRONG_BUY")),
        key=lambda r: r.score,
        reverse=True,
    )[:top]
    sell = sorted(
        (r for r in results if r.action in ("SELL", "STRONG_SELL")),
        key=lambda r: r.score,
    )[:top]
    hold = sorted(
        (r for r in results if r.action == "HOLD"),
        key=lambda r: abs(r.score),
    )[:top]

    return models.ScreenerResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        buy=buy,
        sell=sell,
        hold=hold,
        errors=errors,
    )
