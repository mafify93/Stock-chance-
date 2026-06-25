"""Economic calendar feed — fetches high-impact news events and generates blackout windows.

Uses the ForexFactory unofficial JSON endpoint. Call `refresh_blackout_windows()`
at bot start and on daily reset. The bot's `config.news_blackout_utc` list is
updated in-place so the engine's existing `in_blackout()` check handles the rest.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger(__name__)

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
RELEVANT_CURRENCIES = {"USD", "EUR", "GBP", "JPY"}
MARGIN_MINUTES = 30  # block this many minutes before and after each event


def fetch_blackout_windows(margin_minutes: int = MARGIN_MINUTES) -> list[str]:
    """Return "HH:MM-HH:MM" UTC strings for today's high-impact news events.

    Returns an empty list on any network or parse error so the bot keeps running.
    """
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(CALENDAR_URL)
            resp.raise_for_status()
            events = resp.json()
    except Exception as exc:
        log.warning(f"Economic calendar fetch failed (non-fatal): {exc}")
        return []

    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    windows: list[str] = []
    for ev in events:
        if (ev.get("impact") or "").lower() != "high":
            continue
        currency = (ev.get("currency") or "").upper()
        if currency not in RELEVANT_CURRENCIES:
            continue

        date_str = ev.get("date", "")
        if not date_str.startswith(today_str):
            continue

        try:
            event_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
            event_time = event_time.astimezone(timezone.utc)
        except Exception:
            continue

        start = event_time - timedelta(minutes=margin_minutes)
        end = event_time + timedelta(minutes=margin_minutes)
        window = f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
        windows.append(window)
        log.info(
            f"Calendar: blackout for {currency} '{ev.get('title', '')}' "
            f"at {event_time.strftime('%H:%M')} UTC → window {window}"
        )

    return windows


def refresh_blackout_windows(config) -> None:
    """Fetch today's high-impact events and update config.news_blackout_utc in-place.

    Safe to call on daily reset; any network error is logged and the existing
    windows are left unchanged.
    """
    windows = fetch_blackout_windows()
    config.news_blackout_utc = windows
    log.info(f"Economic calendar: {len(windows)} blackout window(s) active today")
