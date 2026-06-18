"""The forex trading clock.

Unlike the US stock market (one 9:30-16:00 ET session), forex trades 24
hours a day, five days a week, rolling continuously around the globe through
four regional sessions:

    Sydney   22:00 - 07:00 UTC
    Tokyo    00:00 - 09:00 UTC
    London   07:00 - 16:00 UTC
    New York 12:00 - 21:00 UTC

The market "opens" Sunday ~22:00 UTC (Sydney) and "closes" Friday ~21:00 UTC
(New York close). Day traders care most about the *London/New York overlap*
(12:00-16:00 UTC), when liquidity and intraday range are highest, so this
module surfaces which sessions are live and whether the high-liquidity
overlap is active.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta, timezone


@dataclass(frozen=True)
class TradingSession:
    name: str
    open_hour: int   # UTC hour the session opens
    close_hour: int  # UTC hour it closes


SESSIONS = [
    TradingSession("Sydney", 22, 7),
    TradingSession("Tokyo", 0, 9),
    TradingSession("London", 7, 16),
    TradingSession("New York", 12, 21),
]


def _session_active(session: TradingSession, hour: int) -> bool:
    if session.open_hour <= session.close_hour:
        return session.open_hour <= hour < session.close_hour
    # Wraps past midnight (e.g. Sydney 22:00 -> 07:00).
    return hour >= session.open_hour or hour < session.close_hour


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
    """The 24/5 forex week: open from Sunday 22:00 UTC to Friday 21:00 UTC."""
    weekday = now.weekday()  # Mon=0 .. Sun=6
    hour = now.hour
    if weekday == 5:  # Saturday - always closed
        return False
    if weekday == 6:  # Sunday - opens at 22:00 UTC (Sydney)
        return hour >= 22
    if weekday == 4:  # Friday - closes at 21:00 UTC (New York close)
        return hour < 21
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

    hour = now.hour
    active = [s.name for s in SESSIONS if _session_active(s, hour)]
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
