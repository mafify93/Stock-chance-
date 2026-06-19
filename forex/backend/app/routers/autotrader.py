"""HTTP API for the auto-trader bot.

Endpoints
─────────
GET  /api/autotrader/status          current bot state, daily stats, recent trades
POST /api/autotrader/start           start the bot (credentials supplied by the app)
POST /api/autotrader/stop            stop the bot (leaves OANDA orders in place)
PATCH /api/autotrader/config         live-tune config without restarting
POST /api/autotrader/emergency-close stop the bot AND close all bot-originated positions

Security model
──────────────
The app sends the user's OANDA credentials in the StartRequest body; the bot
holds them in memory for the duration of its run. Live trading requires an
explicit acknowledgment flag. Credentials are never written to disk.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..autotrader.config import AutoTraderConfig
from ..autotrader.state import bot_state
from ..providers import oanda

router = APIRouter(prefix="/api/autotrader", tags=["autotrader"])


# ── Request / response models ─────────────────────────────────────────────────


class StartRequest(BaseModel):
    token: str
    account_id: str
    environment: str = "practice"       # "practice" | "live"
    live_trading_acknowledged: bool = False
    # Config overrides — any AutoTraderConfig field can be set here.
    risk_pct: float | None = None
    max_positions: int | None = None
    max_trades_per_day: int | None = None
    daily_loss_limit_pct: float | None = None
    rr_ratio: float | None = None
    max_spread_pips: float | None = None
    min_confidence: float | None = None
    session_filter: bool | None = None
    pairs: list[str] | None = None


class ConfigPatch(BaseModel):
    risk_pct: float | None = None
    max_positions: int | None = None
    max_trades_per_day: int | None = None
    daily_loss_limit_pct: float | None = None
    rr_ratio: float | None = None
    max_spread_pips: float | None = None
    min_confidence: float | None = None
    session_filter: bool | None = None
    min_stop_pips: float | None = None
    max_stop_pips: float | None = None
    pairs: list[str] | None = None


class TradeOut(BaseModel):
    pair: str
    side: str
    units: int
    entry: float
    stop: float
    target: float
    opened_at: str
    trade_id: str
    status: str
    closed_at: str | None = None
    realized_pl: float | None = None


class ConfigOut(BaseModel):
    risk_pct: float
    rr_ratio: float
    min_stop_pips: float
    max_stop_pips: float
    max_positions: int
    max_trades_per_day: int
    daily_loss_limit_pct: float
    min_confidence: float
    max_spread_pips: float
    session_filter: bool
    scan_interval_minutes: int
    pairs: list[str]


class StatusOut(BaseModel):
    running: bool
    halted: bool
    halt_reason: str
    environment: str
    session_date: str | None
    start_of_day_balance: float | None
    daily_pl: float
    trades_today: int
    open_positions: int
    consecutive_losses: int
    risk_scale: float
    config: ConfigOut
    recent_trades: list[TradeOut]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/status", response_model=StatusOut)
async def get_status():
    s = bot_state
    cfg = s.config
    recent = sorted(s.trades, key=lambda t: t.opened_at, reverse=True)[:20]
    return StatusOut(
        running=s.running,
        halted=s.halted,
        halt_reason=s.halt_reason,
        environment=s.environment,
        session_date=s.session_date.isoformat() if s.session_date else None,
        start_of_day_balance=s.start_of_day_balance,
        daily_pl=s.daily_pl,
        trades_today=s.trades_today,
        open_positions=len(s.open_trades),
        consecutive_losses=s.consecutive_losses,
        risk_scale=s.risk_scale,
        config=ConfigOut(**cfg.__dict__),
        recent_trades=[TradeOut(**t.__dict__) for t in recent],
    )


@router.post("/start")
async def start_bot(req: StartRequest):
    if req.environment == "live" and not req.live_trading_acknowledged:
        raise HTTPException(
            400,
            detail=(
                "Live trading requires live_trading_acknowledged=true. "
                "This will place REAL orders with REAL money on your OANDA fxTrade account."
            ),
        )

    cfg = AutoTraderConfig()
    for field in (
        "risk_pct", "max_positions", "max_trades_per_day", "daily_loss_limit_pct",
        "rr_ratio", "max_spread_pips", "min_confidence", "session_filter", "pairs",
    ):
        val = getattr(req, field, None)
        if val is not None:
            setattr(cfg, field, val)

    with bot_state._lock:
        bot_state.token = req.token
        bot_state.account_id = req.account_id
        bot_state.environment = req.environment
        bot_state.config = cfg
        bot_state.running = True
        bot_state.halted = False
        bot_state.halt_reason = ""

    return {
        "status": "started",
        "environment": req.environment,
    }


@router.post("/stop")
async def stop_bot():
    with bot_state._lock:
        bot_state.running = False
    return {"status": "stopped"}


@router.patch("/config")
async def update_config(patch: ConfigPatch):
    cfg = bot_state.config
    updated = []
    for field, val in patch.model_dump(exclude_none=True).items():
        if hasattr(cfg, field):
            setattr(cfg, field, val)
            updated.append(field)
    return {"updated": updated, "config": cfg.__dict__}


@router.post("/emergency-close")
async def emergency_close():
    """Stop the bot and close every open position it originated."""
    state = bot_state

    with state._lock:
        state.running = False
        state.halted = True
        state.halt_reason = "Emergency close triggered at " + datetime.now(timezone.utc).isoformat()

    if not state.token or not state.account_id:
        return {"closed": [], "errors": ["Bot had no credentials — nothing to close"]}

    closed: list[str] = []
    errors: list[str] = []

    for trade in list(state.open_trades):
        try:
            await asyncio.to_thread(
                oanda.close_position,
                state.token,
                state.account_id,
                trade.pair,
                trade.side,
                state.base_url,
            )
            with state._lock:
                trade.status = "closed"
                trade.closed_at = datetime.now(timezone.utc).isoformat()
            closed.append(trade.pair)
        except Exception as exc:
            errors.append(f"{trade.pair}: {exc}")

    return {"closed": closed, "errors": errors}
