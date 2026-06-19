"""In-memory singleton that tracks the bot's runtime state.

Credentials (OANDA token + account ID) are kept here after the user starts
the bot via POST /api/autotrader/start. They are also persisted — encrypted —
by `persistence.py` to a file on a persistent disk, so the bot can auto-resume
after a server restart instead of silently stopping. See that module for the
encryption and key-management details.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from threading import Lock

from .config import AutoTraderConfig


@dataclass
class TradeRecord:
    pair: str
    side: str           # "long" | "short"
    units: int
    entry: float
    stop: float
    target: float
    opened_at: str      # ISO-8601 UTC string
    trade_id: str       # OANDA trade / transaction ID
    status: str = "open"
    closed_at: str | None = None
    realized_pl: float | None = None


@dataclass
class BotState:
    running: bool = False
    token: str = ""
    account_id: str = ""
    environment: str = "practice"   # "practice" | "live"
    config: AutoTraderConfig = field(default_factory=AutoTraderConfig)

    # Daily accounting
    session_date: date | None = None
    start_of_day_balance: float | None = None
    daily_pl: float = 0.0
    trades_today: int = 0
    halted: bool = False
    halt_reason: str = ""

    # Consecutive-loss step-down: risk_pct is multiplied by this factor.
    # McKay rule: 1.0 (normal) → 0.75 → 0.50 → halt.
    risk_scale: float = 1.0
    consecutive_losses: int = 0

    # Full trade log for this server process
    trades: list[TradeRecord] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, compare=False, repr=False)

    @property
    def open_trades(self) -> list[TradeRecord]:
        return [t for t in self.trades if t.status == "open"]

    @property
    def base_url(self) -> str:
        from ..providers.oanda import LIVE_BASE_URL, PRACTICE_BASE_URL
        return PRACTICE_BASE_URL if self.environment == "practice" else LIVE_BASE_URL


# Module-level singleton — shared across all requests and the scheduler job.
bot_state = BotState()
