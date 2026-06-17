"""Earnings sentiment via Claude with web search.

Asks Claude (with the web-search tool enabled) to research a company's most
recent earnings report, guidance, and analyst reactions, then score the
management/market sentiment into a BUY/SELL/HOLD vote. Used as an auxiliary
factor in `app.ai_combine.combine`.

Like `app.ai_analyst`, this is entirely optional and best-effort: it requires
the backend's own `ANTHROPIC_API_KEY`. If unset, `configured()` returns False
and callers simply omit the sentiment factor. Results are cached per
(symbol, day) because earnings sentiment changes slowly and web-search calls
are slow and costly.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = (
    "You are an equity-research assistant inside a trading app called Stock "
    "Chance. Using web search, research the company's MOST RECENT earnings "
    "report: revenue/EPS beats or misses, forward guidance, and how analysts "
    "and the market reacted. Then judge the overall sentiment - is management's "
    "tone and the market's reaction bullish, bearish, or neutral for the stock "
    "right now? Base everything on real, recent information you find via search; "
    "if you cannot find anything material, return HOLD with a low confidence. "
    'Respond with JSON only, no other text: '
    '{"action": "BUY"|"SELL"|"HOLD", "confidence": <0-100 number>, '
    '"summary": "<2-3 sentences on the most recent earnings/guidance and tone>"}'
)

# Module-level cache keyed by (symbol, date.today()).
_cache: dict[tuple[str, date], dict | None] = {}


def configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def get_sentiment(symbol: str) -> dict | None:
    """Returns `{"action", "confidence", "summary", "model"}` or None if not
    configured or the request fails. Cached per (symbol, day)."""
    cache_key = (symbol.upper(), date.today())
    if cache_key in _cache:
        return _cache[cache_key]

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)

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
                "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Research the most recent earnings report and guidance for {symbol} "
                            f"and score the sentiment."
                        ),
                    }
                ],
            },
            timeout=40,  # web search is slow
        )
        response.raise_for_status()
        data = response.json()
        # The response may interleave tool-use/web-search blocks with text;
        # concatenate all text blocks then extract the JSON object.
        text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        )
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("No JSON object found in earnings sentiment response")
        parsed = json.loads(text[start : end + 1])

        action = str(parsed["action"]).upper()
        if action not in ("BUY", "SELL", "HOLD"):
            raise ValueError(f"Unexpected action from earnings sentiment: {action!r}")
        result = {
            "action": action,
            "confidence": max(0.0, min(100.0, float(parsed["confidence"]))),
            "summary": str(parsed["summary"]),
            "model": model,
        }
        _cache[cache_key] = result
        return result
    except Exception:  # noqa: BLE001 - earnings sentiment is best-effort/optional
        logger.exception("Earnings sentiment request failed for %s", symbol)
        return None
