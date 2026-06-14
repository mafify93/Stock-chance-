from __future__ import annotations

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from .. import models
from ..night_scan import night_scan

router = APIRouter(prefix="/api/ai/night-scan", tags=["night-scan"])


@router.get("/status", response_model=models.NightScanStatus)
async def get_status():
    """Latest "Tonight's Picks" deep-research result (if any), plus whether
    the nightly scan is configured (`ANTHROPIC_API_KEY` set) and when it last
    ran / is next scheduled to run."""
    return night_scan.get_status()


@router.post("/run-now", response_model=models.NightScanStatus)
async def run_now():
    """Manually trigger one deep-research scan immediately - useful for
    testing. Normally this runs automatically once per evening (Sunday
    through Thursday, around 8 PM US/Eastern)."""
    await run_in_threadpool(night_scan.run_once)
    return night_scan.get_status()
