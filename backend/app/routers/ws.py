from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from ..providers import yahoo
from ..signals import analyze

logger = logging.getLogger(__name__)
router = APIRouter()

POLL_INTERVAL_SECONDS = 15


@router.websocket("/ws/watch")
async def watch(websocket: WebSocket, symbols: str = Query(..., description="Comma-separated symbols, e.g. AAPL,MSFT")):
    """Stream live quote + buy/sell/hold signal updates for the given symbols.

    Sends one JSON message per symbol every ~15 seconds:
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
            for sym in symbol_list:
                try:
                    quote = await run_in_threadpool(yahoo.get_quote, sym)
                    df = await run_in_threadpool(yahoo.get_history, sym, "6mo", "1d")
                    result = await run_in_threadpool(analyze, sym, df)
                    payload = {
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
                    payload = {"symbol": sym, "error": str(exc)}

                await websocket.send_json(payload)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        logger.info("Client disconnected from /ws/watch")
