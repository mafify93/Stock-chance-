"""LLM-based "AI analyst" - turns the rule-based signal and ML prediction
into a short plain-English buy/sell/hold take with reasoning, via the Claude
API (api.anthropic.com).

This is entirely optional: it requires the user's own `ANTHROPIC_API_KEY`
environment variable on the backend. If it's not set, `configured()` returns
False and `/api/ai/analysis` simply omits the `llm` field - the rule-based
signal and ML prediction still work on their own.
"""
from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = (
    "You are a technical-analysis assistant inside a day-trading app called "
    "Stock Chance. You're given a symbol's current price, a rule-based "
    "technical signal (with reasons), and possibly a machine-learning "
    "model's probability that the price will be higher in N trading days. "
    "Write a short (2-4 sentence) plain-English take: whether this looks "
    "like a buy, sell, or hold right now, your confidence (0-100), and the "
    "single most important reason why, referencing the data you were given. "
    "Always remain grounded in the provided data - do not invent news or "
    "facts you weren't given. This is technical analysis, not a guarantee. "
    'Respond with JSON only, no other text: '
    '{"action": "BUY"|"SELL"|"HOLD", "confidence": <0-100 number>, "summary": "<2-4 sentences>"}'
)


def configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def analyze(symbol: str, signal: dict, ml: dict | None) -> dict | None:
    """Returns `{"action", "confidence", "summary", "model"}` or `None` if
    the AI analyst isn't configured or the request fails."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    payload = {
        "symbol": symbol,
        "price": signal.get("price"),
        "rule_based_signal": {
            "action": signal.get("action"),
            "score": signal.get("score"),
            "confidence": signal.get("confidence"),
            "reasons": signal.get("reasons"),
        },
        "ml_prediction": ml,
    }

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
                "max_tokens": 300,
                "system": _SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": json.dumps(payload)}],
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        )
        parsed = json.loads(text)
        action = str(parsed["action"]).upper()
        if action not in ("BUY", "SELL", "HOLD"):
            raise ValueError(f"Unexpected action from AI analyst: {action!r}")
        return {
            "action": action,
            "confidence": max(0.0, min(100.0, float(parsed["confidence"]))),
            "summary": str(parsed["summary"]),
            "model": model,
        }
    except Exception:  # noqa: BLE001 - AI analyst is best-effort/optional
        logger.exception("AI analyst request failed for %s", symbol)
        return None
