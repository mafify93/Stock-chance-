"""Tonight's Picks: a nightly "deep research" scan.

Every evening, this scan uses Claude's server-side web-search tool
(`web_search_20250305`) to look across a curated universe of liquid,
heavily-covered US stocks/ETFs (see `app.universe.NIGHT_SCAN_UNIVERSE`) for
concrete, recent catalysts - earnings results, guidance changes, product
launches, partnerships/collaborations, M&A, FDA/regulatory decisions, analyst
upgrades/downgrades, major macro events, etc. - and turns them into a short,
concrete shortlist of "what to consider buying tomorrow", each with the
catalyst and a plain-English plan.

=== WHEN IT RUNS ===

Automatically, once per evening (around 8 PM US/Eastern) on evenings before
a US trading day (Sunday through Thursday), so results are ready well within
the 8 PM-11:30 PM window most people check the app the night before. It can
also be triggered manually via `POST /api/ai/night-scan/run-now` (e.g. for
testing) regardless of the time of day.

=== REQUIREMENTS ===

Requires `ANTHROPIC_API_KEY` (the same env var as the optional AI analyst,
see `app.ai_analyst`). If it's not set, the scan is skipped entirely and
`GET /api/ai/night-scan/status` reports `configured: false`.

=== COST NOTE ===

Each scan performs up to `WEB_SEARCH_MAX_USES` web searches via Claude's
web-search tool, which has a small per-search cost in addition to normal
token usage - see Anthropic's pricing docs. Running nightly, this is a
bounded, predictable cost (at most one scan per evening).

=== DISCLAIMER ===

This is speculative, news-driven research, not financial advice. Recent news
and "catalysts" do not guarantee a stock will move in the expected
direction - always do your own research and never risk money you can't
afford to lose.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

import httpx

from . import models
from .intraday import ET
from .universe import NIGHT_SCAN_UNIVERSE

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-6"
WEB_SEARCH_MAX_USES = 8

DATA_DIR = Path(os.environ.get("PERSISTENT_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
RESULT_PATH = DATA_DIR / "night_scan.json"

# Run once per evening, at or after this hour (US/Eastern)...
SCAN_HOUR_ET = 20  # 8 PM ET
# ...on evenings before a US trading day: Sunday (6) through Thursday (3).
SCAN_WEEKDAYS = {6, 0, 1, 2, 3}

LOOP_INTERVAL_SECONDS = 15 * 60

_SYSTEM_PROMPT = (
    "You are a market research analyst for a day-trading app called Stock "
    "Chance. Every evening, you research recent news for a curated list of "
    "US-listed stocks/ETFs to find concrete catalysts - earnings results, "
    "guidance changes, product launches, partnerships/collaborations, M&A, "
    "FDA/regulatory decisions, analyst upgrades/downgrades, major macro or "
    "budget events, etc. - from roughly the last two weeks that could make a "
    "stock move noticeably at the next US market open. Use web search to "
    "check for recent news on the candidates below before you answer - do "
    "not rely only on prior knowledge, since it may be outdated or "
    "incomplete. Then pick the 3-6 stocks with the strongest, most concrete "
    "catalysts. For each, give: a specific action (\"BUY\" if the catalyst is "
    "bullish and recent enough to plausibly move the stock at the next open, "
    "or \"WATCH\" if it's notable but less clear-cut, mixed, or already "
    "priced in), a confidence 0-100, a 1-2 sentence catalyst description "
    "citing what you found and roughly when it happened, and a short "
    "plain-English plan for the next session. Also write a 2-3 sentence "
    "overall summary of the evening's research. Be specific and grounded in "
    "what you actually found via search - if you find nothing compelling for "
    "a symbol, leave it out rather than inventing a reason. This is "
    "speculative research, not financial advice, and is not guaranteed to be "
    "profitable. "
    "Respond with JSON only, no other text, in this exact shape: "
    '{"summary": "<2-3 sentences>", "picks": [{"symbol": "<TICKER>", '
    '"action": "BUY"|"WATCH", "confidence": <0-100 number>, "catalyst": '
    '"<1-2 sentences>", "plan": "<1-2 sentences>"}]}'
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


def _is_scan_time(now: datetime) -> bool:
    return now.weekday() in SCAN_WEEKDAYS and now.hour >= SCAN_HOUR_ET


class NightScanEngine:
    def __init__(self) -> None:
        self._lock = Lock()
        self._task: asyncio.Task | None = None
        self._result = self._load_result()
        self._last_run_date = self._result_date(self._result)

    # --- persistence -------------------------------------------------------

    def _load_result(self) -> dict | None:
        if RESULT_PATH.exists():
            try:
                with open(RESULT_PATH) as f:
                    return json.load(f)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to load night scan result")
        return None

    def _save_result(self, result: dict) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(RESULT_PATH, "w") as f:
            json.dump(result, f, indent=2)
        with self._lock:
            self._result = result
            self._last_run_date = self._result_date(result)

    @staticmethod
    def _result_date(result: dict | None) -> object | None:
        if not result:
            return None
        try:
            return datetime.fromisoformat(result["generated_at"]).astimezone(ET).date()
        except Exception:  # noqa: BLE001
            return None

    # --- status --------------------------------------------------------------

    def get_status(self) -> models.NightScanStatus:
        with self._lock:
            result = self._result
        now = datetime.now(ET)
        return models.NightScanStatus(
            configured=configured(),
            last_run_at=result["generated_at"] if result else None,
            next_run_at=self._next_run_at(now).isoformat(),
            result=models.NightScanResult(**result) if result else None,
        )

    @staticmethod
    def _next_run_at(now: datetime) -> datetime:
        candidate = now.replace(hour=SCAN_HOUR_ET, minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        while candidate.weekday() not in SCAN_WEEKDAYS:
            candidate += timedelta(days=1)
        return candidate

    # --- the scan itself -----------------------------------------------------

    def run_once(self) -> models.NightScanResult | None:
        """Runs one deep-research scan and persists the result. Returns
        `None` (without persisting anything) if `ANTHROPIC_API_KEY` isn't
        configured or the request/parsing fails - safe to call regardless of
        schedule (e.g. a manual "run now" trigger)."""
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None

        model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
        now = datetime.now(ET)
        user_message = (
            f"Today is {now.strftime('%A, %B %d, %Y')} (US/Eastern).\n\n"
            "Candidate symbols (curated, liquid US-listed stocks/ETFs) - "
            "research recent news for these and pick your shortlist from "
            "among them:\n" + ", ".join(NIGHT_SCAN_UNIVERSE)
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
                    "max_tokens": 4000,
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
                timeout=180,
            )
            response.raise_for_status()
            data = response.json()
            text = "".join(
                block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
            )
            parsed = json.loads(_extract_json(text))

            picks: list[dict] = []
            for p in parsed.get("picks", []):
                action = str(p["action"]).upper()
                if action not in ("BUY", "WATCH"):
                    continue
                picks.append(
                    {
                        "symbol": str(p["symbol"]).upper(),
                        "action": action,
                        "confidence": max(0.0, min(100.0, float(p["confidence"]))),
                        "catalyst": str(p["catalyst"]),
                        "plan": str(p["plan"]),
                    }
                )

            result = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "summary": str(parsed.get("summary", "")),
                "picks": picks,
                "model": model,
            }
            self._save_result(result)
            return models.NightScanResult(**result)
        except Exception:  # noqa: BLE001 - best-effort, scan retries next evening
            logger.exception("Night scan failed")
            return None

    # --- background task ------------------------------------------------------

    async def _loop(self) -> None:
        while True:
            try:
                now = datetime.now(ET)
                with self._lock:
                    already_ran_today = self._last_run_date == now.date()
                if configured() and _is_scan_time(now) and not already_ran_today:
                    await asyncio.to_thread(self.run_once)
            except Exception:  # noqa: BLE001
                logger.exception("Night scan loop iteration failed")
            await asyncio.sleep(LOOP_INTERVAL_SECONDS)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None


night_scan = NightScanEngine()
