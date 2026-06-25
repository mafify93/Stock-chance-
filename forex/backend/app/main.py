from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .autotrader.engine import monitor_open_trades, resync_open_trades, scan_and_trade
from .autotrader.persistence import load_into_state, save_state
from .autotrader.state import bot_state
from .routers import autotrader, broker, daytrade, pairs, screener, signal

log = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler(timezone="UTC")


async def _scan_job() -> None:
    """Wrapper so APScheduler can call the async engine."""
    try:
        await scan_and_trade()
        await monitor_open_trades()
        # Checkpoint daily P&L, trade log, and halt state so a restart resumes
        # from where we left off rather than re-trading the day from scratch.
        save_state()
    except Exception as exc:
        log.error(f"AutoTrader scheduler error: {exc}")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    was_running = False
    try:
        was_running = load_into_state()
    except Exception as exc:
        log.error(f"AutoTrader: state reload failed: {exc}")

    interval = bot_state.config.scan_interval_minutes
    _scheduler.add_job(_scan_job, "interval", minutes=interval, id="autotrader_scan")
    _scheduler.start()
    log.info(f"AutoTrader scheduler started (every {interval} min)")

    if was_running and bot_state.token and bot_state.account_id:
        log.info("AutoTrader: persisted state was running — auto-resuming")
        try:
            await resync_open_trades()
        except Exception as exc:
            log.error(f"AutoTrader: auto-resume resync failed: {exc}")

    yield  # app runs here

    # ── Shutdown ──────────────────────────────────────────────────────────────
    _scheduler.shutdown(wait=False)


app = FastAPI(
    title="Forex Chance API",
    description=(
        "Technical-analysis signals (buy/sell/hold), a same-day intraday "
        "engine, a multi-pair screener, OANDA order execution, and a fully "
        "automated trading bot for the Forex Chance iOS/macOS app."
    ),
    version="0.2.0",
    lifespan=_lifespan,
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
