from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

import dataclasses

from ..intraday import compute_day_signal
from ..providers import yahoo
from ..signals import analyze

logger = logging.getLogger(__name__)
router = APIRouter()

POLL_INTERVAL_SECONDS = 10
DAYTRADE_POLL_INTERVAL_SECONDS = 15


async def _fetch_watch_payload(sym: str) -> dict:
    try:
        quote = await run_in_threadpool(yahoo.get_quote, sym)
        df = await run_in_threadpool(yahoo.get_history, sym, "6mo", "1d")
        result = await run_in_threadpool(analyze, sym, df)
        return {
            "symbol": sym,
            "quote": quote,
            "signal": {
                "action": result.action,
                "score": result.score,
                "confidence": result.confidence,
                "reasons": result.reasons,
                "levels": result.levels,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {"symbol": sym, "error": str(exc)}


async def _fetch_daytrade_payload(sym: str) -> dict:
    try:
        df = await run_in_threadpool(yahoo.get_intraday_history, sym)
        result = await run_in_threadpool(compute_day_signal, sym, df)
        return {"symbol": sym, "signal": dataclasses.asdict(result)}
    except Exception as exc:  # noqa: BLE001
        return {"symbol": sym, "error": str(exc)}


@router.websocket("/ws/watch")
async def watch(websocket: WebSocket, symbols: str = Query(..., description="Comma-separated symbols, e.g. AAPL,MSFT")):
    """Stream live quote + buy/sell/hold signal updates for the given symbols.

    Sends one JSON message per symbol every ~10 seconds. All symbols for a
    cycle are fetched concurrently (rather than one-by-one) so a watchlist
    with several symbols doesn't take proportionally longer to refresh:
        {"symbol": "AAPL", "quote": {...}, "signal": {...}}
    or, on a per-symbol error:
        {"symbol": "AAPL", "error": "..."}
    """
    await websocket.accept()
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        await websocket.close(code=1008, reason="No symbols provided")
        return

    try:
        while True:
            payloads = await asyncio.gather(*(_fetch_watch_payload(sym) for sym in symbol_list))
            for payload in payloads:
                await websocket.send_json(payload)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        logger.info("Client disconnected from /ws/watch")


@router.websocket("/ws/daytrade")
async def daytrade_watch(websocket: WebSocket, symbols: str = Query(..., description="Comma-separated symbols, e.g. AAPL,MSFT")):
    """Stream live same-day Buy/Sell/Hold signals (with alerts) for the given symbols.

    Sends one JSON message per symbol every ~15 seconds. All symbols for a
    cycle are fetched concurrently (rather than one-by-one) so a portfolio
    with several positions doesn't take proportionally longer to refresh:
        {"symbol": "AAPL", "signal": {...}}
    or, on a per-symbol error:
        {"symbol": "AAPL", "error": "..."}

    The `signal.alert` field is the key one to watch for positions you've
    marked as "bought": "TAKE_PROFIT_ZONE", "STOP_LOSS_ZONE" or "EOD_EXIT"
    all mean "consider selling now".
    """
    await websocket.accept()
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        await websocket.close(code=1008, reason="No symbols provided")
        return

    try:
        while True:
            payloads = await asyncio.gather(*(_fetch_daytrade_payload(sym) for sym in symbol_list))
            for payload in payloads:
                await websocket.send_json(payload)

            await asyncio.sleep(DAYTRADE_POLL_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        logger.info("Client disconnected from /ws/daytrade")
