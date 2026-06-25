"""The forex trading clock.

Unlike the US stock market (one 9:30-16:00 ET session), forex trades 24
hours a day, five days a week, rolling continuously around the globe through
four regional sessions. Each session is pinned to its financial centre's
*local* clock, so its UTC window shifts by an hour with daylight saving — and
the US and UK switch on different dates, so for ~2 weeks a year the overlap
moves an extra hour. We therefore define sessions in local time and convert,
rather than hardcoding UTC hours (which silently trade the wrong hours around
DST changeovers).

    Sydney   07:00 - 16:00  Australia/Sydney
    Tokyo    09:00 - 18:00  Asia/Tokyo
    London   08:00 - 16:00  Europe/London
    New York 08:00 - 17:00  America/New_York

The market "opens" Sunday ~22:00 UTC (Sydney) and "closes" Friday ~21:00 UTC
(New York close). Day traders care most about the *London/New York overlap*,
when liquidity and intraday range are highest, so this module surfaces which
sessions are live and whether the high-liquidity overlap is active.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class TradingSession:
    name: str
    tz: str          # IANA timezone of the financial centre
    open_hour: int   # local hour the session opens
    close_hour: int  # local hour it closes


SESSIONS = [
    TradingSession("Sydney", "Australia/Sydney", 7, 16),
    TradingSession("Tokyo", "Asia/Tokyo", 9, 18),
    TradingSession("London", "Europe/London", 8, 16),
    TradingSession("New York", "America/New_York", 8, 17),
]

_NY_TZ = ZoneInfo("America/New_York")


def _session_active(session: TradingSession, now_utc: datetime) -> bool:
    """True if `now_utc` falls in the session's local trading window (DST-aware)."""
    local_hour = now_utc.astimezone(ZoneInfo(session.tz)).hour
    if session.open_hour <= session.close_hour:
        return session.open_hour <= local_hour < session.close_hour
    # Wraps past midnight.
    return local_hour >= session.open_hour or local_hour < session.close_hour


def is_rollover(now: datetime | None = None) -> bool:
    """True during the daily interbank rollover (~17:00 New York time), when
    liquidity briefly vanishes and spreads spike. No new entries here."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ny = now.astimezone(_NY_TZ)
    if ny.hour == 16 and ny.minute >= 55:
        return True
    if ny.hour == 17 and ny.minute < 10:
        return True
    return False


def ny_close_imminent(now: datetime | None = None, within_min: int = 5) -> bool:
    """True in the last `within_min` minutes before the 17:00 ET NY session
    close — the cue to flatten intraday positions before the overnight gap.
    DST-aware: this is 20:55 UTC in summer (EDT) and 21:55 UTC in winter (EST)."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ny = now.astimezone(_NY_TZ)
    close = ny.replace(hour=17, minute=0, second=0, microsecond=0)
    minutes_until = (close - ny).total_seconds() / 60
    return 0 <= minutes_until <= within_min


def in_blackout(now: datetime, windows: list[str]) -> bool:
    """True if `now` (UTC) falls in any "HH:MM-HH:MM" UTC blackout window.

    Used for scheduled high-impact news (NFP/CPI/FOMC/ECB) where spreads blow
    out and price gaps. Windows are user-supplied because there's no economic
    calendar feed wired in; an empty list disables the check.
    """
    if not windows:
        return False
    now = now.astimezone(timezone.utc)
    minutes_now = now.hour * 60 + now.minute
    for w in windows:
        try:
            start_s, end_s = w.split("-")
            sh, sm = (int(x) for x in start_s.split(":"))
            eh, em = (int(x) for x in end_s.split(":"))
            start, end = sh * 60 + sm, eh * 60 + em
            if start <= minutes_now <= end:
                return True
        except (ValueError, AttributeError):
            continue  # ignore malformed entries rather than crash the scan
    return False


@dataclass
class MarketSession:
    status: str  # "open" | "closed"
    now_utc: str
    active_sessions: list[str] = field(default_factory=list)
    is_high_liquidity: bool = False  # London/New York overlap (12:00-16:00 UTC)
    minutes_to_close: int | None = None  # to Friday New York close, when open
    minutes_to_open: int | None = None   # to Sunday Sydney open, when closed
    note: str = ""


def _market_is_open(now: datetime) -> bool:
    """The 24/5 forex week: open from Sunday 22:00 UTC to Friday 17:00 ET (DST-aware)."""
    weekday = now.weekday()  # Mon=0 .. Sun=6
    if weekday == 5:  # Saturday - always closed
        return False
    if weekday == 6:  # Sunday - opens at 22:00 UTC (Sydney)
        return now.hour >= 22
    if weekday == 4:  # Friday - closes at 17:00 ET (21:00 UTC EDT, 22:00 UTC EST)
        return now.astimezone(_NY_TZ).hour < 17
    return True  # Mon-Thu - continuously open


def get_market_session(now: datetime | None = None) -> MarketSession:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    iso = now.isoformat()

    if not _market_is_open(now):
        # Next open is Sunday 22:00 UTC.
        days_ahead = (6 - now.weekday()) % 7
        next_open = (now + timedelta(days=days_ahead)).replace(
            hour=22, minute=0, second=0, microsecond=0
        )
        if next_open <= now:
            next_open += timedelta(days=7)
        minutes_to_open = int((next_open - now).total_seconds() // 60)
        return MarketSession(
            status="closed",
            now_utc=iso,
            minutes_to_open=minutes_to_open,
            note="Forex is closed for the weekend. It reopens Sunday 22:00 UTC (Sydney).",
        )

    active = [s.name for s in SESSIONS if _session_active(s, now)]
    high_liquidity = ("London" in active) and ("New York" in active)

    # Friday New York close (21:00 UTC) is the weekly close.
    days_to_friday = (4 - now.weekday()) % 7
    next_close = (now + timedelta(days=days_to_friday)).replace(
        hour=21, minute=0, second=0, microsecond=0
    )
    if next_close <= now:
        next_close += timedelta(days=7)
    minutes_to_close = int((next_close - now).total_seconds() // 60)

    if high_liquidity:
        note = "London/New York overlap - highest liquidity and intraday range of the day."
    elif active:
        note = f"{', '.join(active)} session{'s' if len(active) > 1 else ''} active."
    else:
        note = "Between sessions - liquidity is thin, spreads can widen."

    return MarketSession(
        status="open",
        now_utc=iso,
        active_sessions=active,
        is_high_liquidity=high_liquidity,
        minutes_to_close=minutes_to_close,
        note=note,
    )
