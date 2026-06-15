"""Ask the AI: a conversational chat backed by Claude, grounded in the live
data shown in the app - the user's positions, watchlist, current signals, and
the AI auto-trader's recent activity.

This is entirely optional: it requires the user's own `ANTHROPIC_API_KEY`
environment variable on the backend (the same one used by the AI analyst and
Tonight's Picks). If it's not set, `configured()` returns False and
`POST /api/ai/chat` responds with 400.
"""
from __future__ import annotations

import json
import logging
import os

import httpx

from . import ai_context, models

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-6"

# Only send the most recent turns to keep prompts (and cost) bounded.
MAX_HISTORY_MESSAGES = 20

_SYSTEM_PROMPT = (
    "You are the in-app AI assistant for a day-trading app called Stock "
    "Chance. Answer the user's questions about their portfolio, watchlist, "
    "the AI auto-trader's recent activity, and current technical signals, "
    "using the live data provided in the context message plus your general "
    "knowledge of markets and trading concepts. Be concise (usually 2-5 "
    "sentences) and specific - reference the actual numbers, signals, and "
    "reasons you were given rather than speaking in generalities. If asked "
    "about something the context doesn't cover (e.g. breaking news you "
    "weren't given), say you don't have live data for that rather than "
    "guessing. Never claim a trade or strategy is guaranteed to be "
    "profitable - this is automated technical analysis and trading activity, "
    "not financial advice."
)


def configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _build_context(context: models.AIChatContext) -> dict:
    symbols = ai_context.dedupe_symbols([p.symbol for p in context.positions], context.watchlist)
    return {
        "positions": [p.model_dump() for p in context.positions],
        "watchlist": [s.upper() for s in context.watchlist],
        "signals": [s for s in (ai_context.symbol_snapshot(sym) for sym in symbols) if s],
        "auto_trader": ai_context.auto_trader_summary(),
    }


def chat(messages: list[models.ChatMessage], context: models.AIChatContext) -> str | None:
    """Returns the assistant's reply text, or `None` if AI chat isn't
    configured or the request fails."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    context_message = "Live data from the app right now (JSON):\n" + json.dumps(_build_context(context))

    api_messages: list[dict] = [
        {"role": "user", "content": context_message},
        {"role": "assistant", "content": "Got it - I'll use this data to answer your questions."},
    ]
    for m in messages[-MAX_HISTORY_MESSAGES:]:
        role = "user" if m.role == "user" else "assistant"
        api_messages.append({"role": role, "content": m.content})

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
                "max_tokens": 600,
                "system": _SYSTEM_PROMPT,
                "messages": api_messages,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        ).strip()
        return text or None
    except Exception:  # noqa: BLE001 - chat is best-effort
        logger.exception("AI chat request failed")
        return None
