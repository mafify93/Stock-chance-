from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from .. import daily_briefing, models

router = APIRouter(prefix="/api/ai/daily-briefing", tags=["daily-briefing"])


@router.get("/status", response_model=models.AIFeatureStatus)
async def get_status():
    """Whether the Daily AI Briefing is configured (`ANTHROPIC_API_KEY` set)."""
    return models.AIFeatureStatus(configured=daily_briefing.configured())


@router.post("", response_model=models.DailyBriefingResponse)
async def get_daily_briefing(request: models.DailyBriefingRequest):
    """Generate today's personalized AI briefing for the given holdings and
    watchlist - what's notable, what moved overnight and why (via web
    search), and what to watch today. Requires `ANTHROPIC_API_KEY`."""
    if not daily_briefing.configured():
        raise HTTPException(status_code=400, detail="Daily Briefing requires ANTHROPIC_API_KEY to be configured on the backend")
    result = await run_in_threadpool(daily_briefing.generate, request)
    if result is None:
        raise HTTPException(status_code=502, detail="Daily briefing generation failed - please try again")
    return result
