from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from .. import models
from ..intraday import compute_day_signal, get_market_session
from ..morning_scan import evaluate_candidate
from ..providers import yahoo
from ..signals import analyze
from ..top_pick import evaluate_opportunity
from ..universe import DAYTRADE_UNIVERSE

router = APIRouter(prefix="/api/daytrade", tags=["daytrade"])

_CONCURRENCY = 8


@router.get("/session", response_model=models.MarketSessionResponse)
async def session():
    """Current US market session (pre-market / open / after-hours / closed)."""
    return dataclasses.asdict(get_market_session())


@router.get("/signal/{symbol}", response_model=models.DaySignalResponse)
async def day_signal(symbol: str):
    """Same-day Buy/Sell/Hold signal from today's intraday (5-minute) price action.

    Designed for a "buy after the open, sell before the close" style of
    trading: VWAP position, opening-range breakout, short-term momentum
    (EMA crossover), intraday RSI dips/peaks, and volume spikes - plus a
    suggested target/stop and an end-of-day exit reminder.
    """
    symbol = symbol.upper()
    try:
        df = await run_in_threadpool(yahoo.get_intraday_history, symbol)
        result = await run_in_threadpool(compute_day_signal, symbol, df)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Day signal computation failed: {exc}") from exc

    data = dataclasses.asdict(result)
    return data


@router.get("/intraday/{symbol}", response_model=list[models.Candle])
async def intraday_history(symbol: str, period: str = "1d", interval: str = "5m"):
    """5-minute (or other) intraday candles for the current/most recent session, for charting."""
    symbol = symbol.upper()
    try:
        df = await run_in_threadpool(yahoo.get_intraday_history, symbol, period, interval)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Intraday history lookup failed: {exc}") from exc

    return [
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


@router.get("/morning", response_model=models.MorningScanResponse)
async def morning_scan(
    symbols: str | None = Query(
        None,
        description="Comma-separated list of symbols to scan. Defaults to a curated set of liquid, volatile stocks/ETFs.",
    ),
    top: int = Query(8, ge=1, le=20, description="Max number of results per bucket"),
):
    """"What to buy when the market opens" - a morning watchlist.

    Combines each symbol's longer-term daily trend with its overnight /
    pre-market price move to highlight same-day buy candidates, each with a
    suggested entry plan and a rough "suspected profit" target based on the
    stock's typical daily volatility.
    """
    symbol_list = (
        [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if symbols
        else DAYTRADE_UNIVERSE
    )

    sem = asyncio.Semaphore(_CONCURRENCY)
    candidates: list[models.MorningCandidate] = []
    errors: dict[str, str] = {}

    async def process(sym: str) -> None:
        async with sem:
            try:
                daily_df = await run_in_threadpool(yahoo.get_history, sym, "6mo", "1d")
                premarket = await run_in_threadpool(yahoo.get_premarket_info, sym)
                candidate = await run_in_threadpool(evaluate_candidate, sym, daily_df, premarket)
                candidates.append(models.MorningCandidate(**dataclasses.asdict(candidate)))
            except Exception as exc:  # noqa: BLE001
                errors[sym] = str(exc)

    await asyncio.gather(*(process(sym) for sym in symbol_list))

    buy_at_open = sorted(
        (c for c in candidates if c.action == "BUY_AT_OPEN"),
        key=lambda c: c.daily_score, reverse=True,
    )
    watch = sorted(
        (c for c in candidates if c.action == "WATCH_DIP"),
        key=lambda c: c.daily_score, reverse=True,
    )
    avoid = sorted(
        (c for c in candidates if c.action == "AVOID"),
        key=lambda c: c.daily_score,
    )

    return models.MorningScanResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        session=dataclasses.asdict(get_market_session()),
        buy_at_open=buy_at_open[:top],
        watch=watch[:top],
        avoid=avoid[:top],
        errors=errors,
    )


@router.get("/top-pick", response_model=models.TopPickResponse)
async def top_pick(
    symbols: str | None = Query(
        None,
        description="Comma-separated list of symbols to scan. Defaults to a curated set of liquid, volatile stocks/ETFs.",
    ),
    count: int = Query(3, ge=1, le=10, description="How many ranked ideas to return"),
):
    """The single best (and next-best) trade ideas right now.

    Combines the longer-term daily trend, today's intraday momentum, and
    analyst price targets into one ranked "what to do right now" idea per
    symbol, then returns the top-ranked ideas with a plain-language summary.
    """
    symbol_list = (
        [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if symbols
        else DAYTRADE_UNIVERSE
    )

    sem = asyncio.Semaphore(_CONCURRENCY)
    opportunities: list[models.Opportunity] = []
    errors: dict[str, str] = {}

    async def process(sym: str) -> None:
        async with sem:
            try:
                daily_df = await run_in_threadpool(yahoo.get_history, sym, "6mo", "1d")
                daily = await run_in_threadpool(analyze, sym, daily_df)

                day_result = None
                try:
                    intraday_df = await run_in_threadpool(yahoo.get_intraday_history, sym)
                    day_result = await run_in_threadpool(compute_day_signal, sym, intraday_df)
                except Exception:  # noqa: BLE001 - intraday data is best-effort
                    pass

                analyst = await run_in_threadpool(yahoo.get_analyst_outlook, sym)

                change_percent = None
                try:
                    quote = await run_in_threadpool(yahoo.get_quote, sym)
                    change_percent = quote.get("change_percent")
                except Exception:  # noqa: BLE001
                    pass

                opp = evaluate_opportunity(sym, daily, day_result, analyst, change_percent)
                opportunities.append(models.Opportunity(**dataclasses.asdict(opp)))
            except Exception as exc:  # noqa: BLE001
                errors[sym] = str(exc)

    await asyncio.gather(*(process(sym) for sym in symbol_list))

    ranked = sorted(opportunities, key=lambda o: o.opportunity_score, reverse=True)

    return models.TopPickResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        session=dataclasses.asdict(get_market_session()),
        picks=ranked[:count],
        errors=errors,
    )
