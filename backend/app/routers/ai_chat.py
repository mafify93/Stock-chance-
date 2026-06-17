from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from .. import ai_chat, models

router = APIRouter(prefix="/api/ai/chat", tags=["ai-chat"])


@router.get("/status", response_model=models.AIFeatureStatus)
async def get_status():
    """Whether "Ask the AI" chat is configured (`ANTHROPIC_API_KEY` set)."""
    return models.AIFeatureStatus(configured=ai_chat.configured())


@router.post("", response_model=models.AIChatResponse)
async def chat(request: models.AIChatRequest):
    """Ask the AI a question about your portfolio, watchlist, the
    auto-trader's recent activity, or current signals. The app sends your
    current positions and watchlist as `context`; the backend adds live
    signals for those symbols plus a summary of the auto-trader's recent
    decisions before asking Claude. Requires `ANTHROPIC_API_KEY`."""
    if not ai_chat.configured():
        raise HTTPException(status_code=400, detail="AI chat requires ANTHROPIC_API_KEY to be configured on the backend")
    reply = await run_in_threadpool(ai_chat.chat, request.messages, request.context)
    if reply is None:
        raise HTTPException(status_code=502, detail="AI chat request failed - please try again")
    return models.AIChatResponse(reply=reply)
