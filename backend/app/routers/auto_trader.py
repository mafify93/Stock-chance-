from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from .. import models
from ..auto_trader import auto_trader

router = APIRouter(prefix="/api/ai/auto-trader", tags=["auto-trader"])


@router.get("/config", response_model=models.AutoTraderConfig)
async def get_config():
    """Current auto-trader configuration. Credentials are never returned -
    only whether Alpaca credentials are configured."""
    return auto_trader.get_config()


@router.post("/config", response_model=models.AutoTraderConfig)
async def update_config(config: models.AutoTraderConfigRequest):
    """Update the auto-trader configuration. Disabled by default - placing
    REAL orders also requires `environment: "live"` AND
    `confirmed_real_money: true`. Omit `alpaca_api_key_id` /
    `alpaca_api_secret_key` to leave previously-saved credentials unchanged."""
    try:
        return auto_trader.update_config(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status", response_model=models.AutoTraderStatus)
async def get_status():
    """Current config plus the most recent decisions (including HOLDs and
    skipped trades with the reason why) and today's executed-trade count."""
    return auto_trader.get_status()


@router.post("/run-now", response_model=models.AutoTraderStatus)
async def run_now():
    """Manually trigger one evaluation cycle immediately, regardless of the
    poll interval - useful for testing a configuration. Runs even if
    `enabled` is false (the background loop is what respects `enabled`), but
    still only acts while the market is open."""
    await run_in_threadpool(auto_trader.run_once)
    return auto_trader.get_status()
