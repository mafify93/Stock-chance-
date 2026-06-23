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

from ..autotrader.backtest import run_backtest
from ..autotrader.config import AutoTraderConfig
from ..autotrader.engine import resync_open_trades
from ..autotrader.learner import trade_learner
from ..autotrader.persistence import save_state
from ..autotrader.state import bot_state
from ..providers import oanda
from ..providers.oanda import LIVE_BASE_URL, PRACTICE_BASE_URL

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
    rr_ratio: float | None = None
    max_spread_pips: float | None = None
    min_confidence: float | None = None
    session_filter: bool | None = None
    pairs: list[str] | None = None


class ConfigPatch(BaseModel):
    risk_pct: float | None = None
    max_positions: int | None = None
    max_trades_per_day: int | None = None
    rr_ratio: float | None = None
    max_spread_pips: float | None = None
    min_confidence: float | None = None
    session_filter: bool | None = None
    min_stop_pips: float | None = None
    max_stop_pips: float | None = None
    pairs: list[str] | None = None
    signal_confirmation: bool | None = None
    partial_tp: bool | None = None
    time_decay_stop: bool | None = None
    max_trade_hours: float | None = None
    block_rollover: bool | None = None
    news_blackout_utc: list[str] | None = None
    trail_runner: bool | None = None
    trail_atr_period: int | None = None
    trail_atr_mult: float | None = None
    use_london_breakout: bool | None = None
    london_breakout_pairs: list[str] | None = None
    use_ai_learner: bool | None = None
    ai_min_win_prob: float | None = None
    profit_lock_pips: float | None = None
    use_ict_sweep: bool | None = None
    use_orb: bool | None = None
    use_silver_bullet: bool | None = None
    use_order_blocks: bool | None = None


class BacktestRequest(BaseModel):
    token: str
    account_id: str
    environment: str = "practice"        # candles come from the chosen environment
    pairs: list[str] | None = None       # defaults to the live config's pair list
    bars: int = 2000                     # M5 bars of history per pair (~7 trading days)
    spread_pips: float = 1.0             # round-trip spread cost charged per trade
    starting_nav: float = 1000.0
    # Strategy overrides — default to the live AutoTraderConfig values.
    risk_pct: float | None = None
    rr_ratio: float | None = None
    min_confidence: float | None = None
    session_filter: bool | None = None
    h1_trend_filter: bool | None = None  # toggle the H1 trend filter for A/B tests
    breakeven_stop: bool | None = None   # toggle the 1R break-even stop for A/B tests
    max_trades_per_day: int | None = None
    min_stop_pips: float | None = None
    max_stop_pips: float | None = None


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
    daily_loss_limit_pct: float = 0.0   # kept for iOS backward-compat; feature removed
    min_confidence: float
    max_spread_pips: float
    session_filter: bool
    scan_interval_minutes: int
    pairs: list[str]
    signal_confirmation: bool
    partial_tp: bool
    time_decay_stop: bool
    max_trade_hours: float
    block_rollover: bool
    news_blackout_utc: list[str]
    trail_runner: bool
    trail_atr_period: int
    trail_atr_mult: float
    profit_lock_pips: float
    use_london_breakout: bool
    london_breakout_pairs: list[str]
    use_ai_learner: bool
    ai_min_win_prob: float
    use_ict_sweep: bool
    use_orb: bool
    use_silver_bullet: bool
    use_order_blocks: bool


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
        "risk_pct", "max_positions", "max_trades_per_day",
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

    # Re-populate open trades from OANDA so guards stay accurate after restarts.
    await resync_open_trades()

    # Persist so the bot auto-resumes if the server restarts.
    save_state()

    return {
        "status": "started",
        "environment": req.environment,
    }


@router.post("/stop")
async def stop_bot():
    with bot_state._lock:
        bot_state.running = False
    save_state()  # persist the stop so a restart doesn't auto-resume
    return {"status": "stopped"}


@router.patch("/config")
async def update_config(patch: ConfigPatch):
    cfg = bot_state.config
    updated = []
    for field, val in patch.model_dump(exclude_none=True).items():
        if hasattr(cfg, field):
            setattr(cfg, field, val)
            updated.append(field)
    save_state()
    return {"updated": updated, "config": cfg.__dict__}


@router.post("/backtest")
async def backtest(req: BacktestRequest):
    """Replay historical M5 candles through the strategy with spread costs.

    Returns realised expectancy (net pips per trade), win rate, profit factor,
    and the equity curve's max drawdown — the numbers that tell you whether the
    strategy has a real edge *after* the spread, before risking live money.
    """
    base_url = PRACTICE_BASE_URL if req.environment == "practice" else LIVE_BASE_URL

    cfg = AutoTraderConfig()
    for field in (
        "risk_pct", "rr_ratio", "min_confidence", "session_filter",
        "h1_trend_filter", "breakeven_stop",
        "max_trades_per_day", "min_stop_pips", "max_stop_pips",
    ):
        val = getattr(req, field, None)
        if val is not None:
            setattr(cfg, field, val)

    pairs = req.pairs or cfg.pairs
    bars = max(100, min(req.bars, 5000))  # OANDA caps a single candle request

    candles_by_pair: dict = {}
    h1_by_pair: dict = {}
    errors: list[str] = []

    async def _load_pair(pair: str) -> None:
        try:
            df = await asyncio.to_thread(
                oanda.get_candles, pair, req.token, "M5", bars, base_url
            )
            if len(df) >= 50:
                candles_by_pair[pair] = df
            else:
                errors.append(f"{pair}: only {len(df)} M5 bars returned, skipped")
        except Exception as exc:
            errors.append(f"{pair}: {exc}")
        if cfg.h1_trend_filter:
            try:
                df_h1 = await asyncio.to_thread(
                    oanda.get_candles, pair, req.token, "H1", 500, base_url
                )
                if len(df_h1) >= 50:
                    h1_by_pair[pair] = df_h1
            except Exception:
                pass  # H1 is optional; the filter degrades gracefully without it

    await asyncio.gather(*[_load_pair(p) for p in pairs])

    if not candles_by_pair:
        raise HTTPException(
            502, detail=f"Could not load candles for backtest. {'; '.join(errors) or ''}"
        )

    spread_by_pair = {p: req.spread_pips for p in candles_by_pair}
    result = await asyncio.to_thread(
        run_backtest, candles_by_pair, cfg, spread_by_pair, req.starting_nav,
        h1_by_pair or None,
    )
    result["errors"] = errors
    result["bars_per_pair"] = bars
    return result


@router.post("/reset-day")
async def reset_day():
    """Reset today's trade counter and P&L so the bot can take new entries.

    Use this when the daily cap has been consumed (e.g. due to tight stops getting
    hit repeatedly) and you want to continue trading the same session without
    restarting the server.
    """
    from datetime import date
    with bot_state._lock:
        bot_state.trades_today = 0
        bot_state.daily_pl = 0.0
        bot_state.consecutive_losses = 0
        bot_state.risk_scale = 1.0
        bot_state.halted = False
        bot_state.halt_reason = ""
        bot_state.session_date = date.today()
    return {"status": "reset", "trades_today": 0, "risk_scale": 1.0}


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

    save_state()  # persist halted state so a restart stays halted
    return {"closed": closed, "errors": errors}


@router.get("/learner-stats")
async def learner_stats():
    """Return the AI learner's current state: win rate, model activation, feature importances."""
    return trade_learner.stats()
