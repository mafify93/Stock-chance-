from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .autotrader.engine import monitor_open_trades, scan_and_trade
from .autotrader.state import bot_state
from .routers import autotrader, broker, daytrade, pairs, screener, signal

log = logging.getLogger(__name__)

app = FastAPI(
    title="Forex Chance API",
    description=(
        "Technical-analysis signals (buy/sell/hold), a same-day intraday "
        "engine, a multi-pair screener, OANDA order execution, and a fully "
        "automated trading bot for the Forex Chance iOS/macOS app."
    ),
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pairs.router)
app.include_router(signal.router)
app.include_router(screener.router)
app.include_router(daytrade.router)
app.include_router(broker.router)
app.include_router(autotrader.router)

# ── APScheduler — runs the auto-trader scan every 5 min ──────────────────────

_scheduler = AsyncIOScheduler(timezone="UTC")


async def _scan_job() -> None:
    """Wrapper so APScheduler can call the async engine."""
    try:
        await scan_and_trade()
        await monitor_open_trades()
    except Exception as exc:
        log.error(f"AutoTrader scheduler error: {exc}")


@app.on_event("startup")
async def _startup() -> None:
    interval = bot_state.config.scan_interval_minutes
    _scheduler.add_job(_scan_job, "interval", minutes=interval, id="autotrader_scan")
    _scheduler.start()
    log.info(f"AutoTrader scheduler started (every {interval} min)")


@app.on_event("shutdown")
async def _shutdown() -> None:
    _scheduler.shutdown(wait=False)


# ── Health / root ─────────────────────────────────────────────────────────────


@app.get("/")
async def root():
    return {
        "name": "Forex Chance API",
        "status": "ok",
        "docs": "/docs",
        "disclaimer": (
            "Educational use only. Not financial advice. Leveraged forex "
            "trading carries a high risk of losing money rapidly."
        ),
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
