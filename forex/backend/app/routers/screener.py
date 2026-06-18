from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query
from fastapi.concurrency import run_in_threadpool

from .. import models, pips
from ..intraday import compute_day_signal
from ..providers import oanda
from ..signals import analyze
from ..universe import DEFAULT_UNIVERSE
from . import deps

router = APIRouter(prefix="/api", tags=["screener"])

_CONCURRENCY = 6


@router.get("/screener", response_model=models.ScreenerResponse)
async def screener(
    pairs: str | None = Query(
        None,
        description="Comma-separated pairs to scan (e.g. 'EUR_USD,GBP_JPY'). Defaults to the major + minor universe.",
    ),
    top: int = Query(10, ge=1, le=30, description="Max results per bucket (buy/sell/hold)"),
    token: str = Depends(deps.oanda_token),
    oanda_api_env: str | None = Header(None, alias="Oanda-Api-Env"),
):
    """Scan many pairs at once and rank them into Buy / Sell / Hold buckets.

    Runs the same swing signal engine as /api/signal across the whole
    universe (or a custom list) and sorts by score. The intraday change (in
    pips since the UTC open) is attached when available.
    """
    url = deps.base_url(oanda_api_env)
    pair_list = (
        [pips.normalize(p) for p in pairs.split(",") if p.strip()]
        if pairs
        else DEFAULT_UNIVERSE
    )

    sem = asyncio.Semaphore(_CONCURRENCY)
    results: list[models.ScreenerItem] = []
    errors: dict[str, str] = {}

    async def process(pair: str) -> None:
        async with sem:
            try:
                df = await run_in_threadpool(oanda.get_candles, pair, token, "H1", 400, url)
                result = await run_in_threadpool(analyze, pair, df)

                change_pips = None
                try:
                    m5 = await run_in_threadpool(oanda.get_candles, pair, token, "M5", 300, url)
                    day = await run_in_threadpool(compute_day_signal, pair, m5)
                    change_pips = day.change_from_open_pips
                except Exception:  # noqa: BLE001 - intraday is best-effort
                    pass

                results.append(
                    models.ScreenerItem(
                        pair=result.pair,
                        display=pips.display(result.pair),
                        action=result.action,
                        score=result.score,
                        confidence=result.confidence,
                        price=result.price,
                        change_from_open_pips=change_pips,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                errors[pips.display(pair)] = str(exc)

    await asyncio.gather(*(process(p) for p in pair_list))

    buy = sorted(
        (r for r in results if r.action in ("BUY", "STRONG_BUY")),
        key=lambda r: r.score, reverse=True,
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
