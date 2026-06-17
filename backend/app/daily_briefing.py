"""Daily AI Briefing: a personalized morning summary of the user's holdings
and watchlist.

This builds on the same Claude + web-search pattern as Tonight's Picks
(`app.night_scan`), but instead of scanning a generic curated universe once
per evening, it's generated on demand for whatever holdings/watchlist the app
sends - so it stays personal even though the backend itself doesn't persist
the user's positions (those live on-device).

Requires `ANTHROPIC_API_KEY` (the same env var as the AI analyst, Tonight's
Picks, and Ask the AI chat). If it's not set, `configured()` returns False and
`POST /api/ai/daily-briefing` responds with 400.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import httpx

from . import ai_context, models
from .night_scan import night_scan

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-6"
WEB_SEARCH_MAX_USES = 4

_SYSTEM_PROMPT = (
    "You are the in-app AI assistant for a day-trading app called Stock "
    "Chance, writing the user's personalized morning briefing. You're given "
    "the user's current holdings (with entry price and live signal data), "
    "watchlist signals, the AI auto-trader's recent activity, and last "
    "night's research scan (if any). If anything looks like it moved "
    "notably or a signal changed, use web search to check for recent news on "
    "those specific symbols. Then write a short (3-6 sentence) plain-English "
    "morning briefing: what's notable about the user's holdings/watchlist "
    "right now, what (if anything) moved overnight and why, and what to "
    "watch today. Be specific and grounded in the data you were given and "
    "what you find via search - if nothing notable happened for a holding, "
    "don't force a comment about it. This is technical analysis and "
    "automated research, not financial advice. "
    'Respond with JSON only, no other text: {"briefing": "<3-6 sentences>"}'
)


def configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _extract_json(text: str) -> str:
    """Best-effort extraction of a JSON object from the model's response - in
    case it adds stray text despite being asked for JSON only."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in AI response")
    return text[start : end + 1]


def _build_context(request: models.DailyBriefingRequest) -> dict:
    holdings = []
    for p in request.positions:
        snap = ai_context.symbol_snapshot(p.symbol.upper()) or {"symbol": p.symbol.upper()}
        snap["quantity"] = p.quantity
        snap["avg_entry_price"] = p.avg_entry_price
        holdings.append(snap)

    held_symbols = {p.symbol.upper() for p in request.positions}
    watch_symbols = ai_context.dedupe_symbols([s for s in request.watchlist if s.upper() not in held_symbols])
    watchlist_signals = [s for s in (ai_context.symbol_snapshot(sym) for sym in watch_symbols) if s]

    night_status = night_scan.get_status()
    tonights_picks = None
    if night_status.result:
        tonights_picks = {
            "summary": night_status.result.summary,
            "picks": [
                {"symbol": p.symbol, "action": p.action, "catalyst": p.catalyst}
                for p in night_status.result.picks
            ],
        }

    return {
        "holdings": holdings,
        "watchlist": watchlist_signals,
        "auto_trader": ai_context.auto_trader_summary(),
        "tonights_picks": tonights_picks,
    }


def generate(request: models.DailyBriefingRequest) -> models.DailyBriefingResponse | None:
    """Returns today's personalized briefing, or `None` if AI features aren't
    configured or the request/parsing fails."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    now = datetime.now(timezone.utc)
    user_message = (
        f"Today is {now.strftime('%A, %B %d, %Y')} (UTC). Here is the user's "
        "current portfolio/watchlist data and recent AI activity (JSON). "
        "Write today's morning briefing:\n" + json.dumps(_build_context(request))
    )

    try:
        response = httpx.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 700,
                "system": _SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_message}],
                "tools": [
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": WEB_SEARCH_MAX_USES,
                    }
                ],
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        )
        parsed = json.loads(_extract_json(text))
        return models.DailyBriefingResponse(
            generated_at=now.isoformat(),
            briefing=str(parsed["briefing"]),
            model=model,
        )
    except Exception:  # noqa: BLE001 - best-effort, caller can retry
        logger.exception("Daily briefing generation failed")
        return None
