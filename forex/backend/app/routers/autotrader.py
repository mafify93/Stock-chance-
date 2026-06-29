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
from ..autotrader.learner import TradeFeatures, trade_learner
from ..autotrader.persistence import save_state
from ..autotrader.state import bot_state
from ..providers import oanda
from ..providers.oanda import LIVE_BASE_URL, PRACTICE_BASE_URL
from ..autotrader import telegram

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
    prop_mode: bool | None = None


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
    hwm_close: bool | None = None
    hwm_r: float | None = None
    breakeven_stop: bool | None = None
    breakeven_r: float | None = None
    use_ict_sweep: bool | None = None
    use_orb: bool | None = None
    use_silver_bullet: bool | None = None
    use_order_blocks: bool | None = None
    daily_loss_halt_pct: float | None = None
    use_atr_expansion_filter: bool | None = None
    atr_expansion_lookback: int | None = None
    h1_trend_filter: bool | None = None
    block_ema_ny_open: bool | None = None
    use_ny_open_momentum_filter: bool | None = None
    ema_session_window: bool | None = None
    use_ema_fallback: bool | None = None
    prop_mode: bool | None = None
    prop_daily_loss_pct: float | None = None
    prop_max_total_loss_pct: float | None = None
    prop_profit_target_pct: float | None = None


class BacktestRequest(BaseModel):
    token: str
    account_id: str
    environment: str = "practice"        # candles come from the chosen environment
    pairs: list[str] | None = None       # defaults to the live config's pair list
    bars: int = 2000                     # M5 bars of history per pair (~7 trading days)
    spread_pips: float = 1.0             # round-trip spread cost charged per trade
    slippage_pips: float = 0.5           # adverse entry + stop slippage per trade
    walk_forward_pct: float = 0.3        # hold-out fraction for out-of-sample validation (0 = disabled)
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
    use_atr_expansion_filter: bool | None = None
    use_ny_open_momentum_filter: bool | None = None
    ema_session_window: bool | None = None
    use_ema_fallback: bool | None = None
    use_london_breakout: bool | None = None


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
    breakeven_stop: bool
    breakeven_r: float
    partial_tp: bool
    time_decay_stop: bool
    max_trade_hours: float
    block_rollover: bool
    news_blackout_utc: list[str]
    trail_runner: bool
    trail_atr_period: int
    trail_atr_mult: float
    profit_lock_pips: float
    hwm_close: bool
    hwm_r: float
    use_london_breakout: bool
    london_breakout_pairs: list[str]
    use_ai_learner: bool
    ai_min_win_prob: float
    use_ict_sweep: bool
    use_orb: bool
    use_silver_bullet: bool
    use_order_blocks: bool
    daily_loss_halt_pct: float
    use_atr_expansion_filter: bool
    atr_expansion_lookback: int
    h1_trend_filter: bool
    block_ema_ny_open: bool
    use_ny_open_momentum_filter: bool
    ema_session_window: bool
    use_ema_fallback: bool
    prop_mode: bool = False
    prop_daily_loss_pct: float = 0.04
    prop_max_total_loss_pct: float = 0.08
    prop_profit_target_pct: float = 0.10


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
        "prop_mode",
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
        # Fresh start = fresh challenge: re-base the prop max-loss / target floor
        # on the next scan's NAV (cleared here so the engine recaptures it).
        bot_state.account_start_balance = None

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
        "use_atr_expansion_filter", "use_ny_open_momentum_filter",
        "ema_session_window", "use_ema_fallback", "use_london_breakout",
    ):
        val = getattr(req, field, None)
        if val is not None:
            setattr(cfg, field, val)

    pairs = req.pairs or cfg.pairs
    # Cap bars at 3000 (≈10 trading days): beyond this the computation time on
    # a shared Render instance exceeds mobile client timeouts without adding
    # meaningful statistical sample size. 5000-bar backtests can be run by
    # lowering bars in the app settings.
    bars = max(100, min(req.bars, 3000))

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

    # 55-second hard deadline: OANDA fetch (≤20s) + compute (≤25s) + buffer.
    # Returns a clear 504 rather than silently hanging until the mobile client
    # times out and shows a generic network error.
    try:
        await asyncio.wait_for(
            asyncio.gather(*[_load_pair(p) for p in pairs]),
            timeout=55,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            504,
            detail="Backtest timed out fetching candles. Try fewer bars or check your connection.",
        )

    if not candles_by_pair:
        raise HTTPException(
            502, detail=f"Could not load candles for backtest. {'; '.join(errors) or ''}"
        )

    spread_by_pair = {p: req.spread_pips for p in candles_by_pair}
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                run_backtest, candles_by_pair, cfg, spread_by_pair, req.starting_nav,
                h1_by_pair or None,
                req.slippage_pips,
                req.walk_forward_pct,
            ),
            timeout=55,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            504,
            detail="Backtest computation timed out. Try reducing the number of bars.",
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
            realized_pl = 0.0
            try:
                trade_data = await asyncio.to_thread(
                    oanda.get_trade,
                    state.token, state.account_id, trade.trade_id, state.base_url,
                )
                realized_pl = float(trade_data.get("realizedPL") or 0)
            except Exception:
                pass
            with state._lock:
                trade.status = "closed"
                trade.closed_at = datetime.now(timezone.utc).isoformat()
                trade.realized_pl = realized_pl
                state.daily_pl += realized_pl
                if realized_pl < 0:
                    state.consecutive_losses += 1
                elif realized_pl > 0:
                    state.consecutive_losses = 0
            if trade.entry_features:
                try:
                    features = TradeFeatures.from_dict(trade.entry_features)
                    trade_learner.record(features, realized_pl)
                except Exception:
                    pass
            telegram.notify_trade_close(trade.pair, trade.side, realized_pl)
            closed.append(trade.pair)
        except Exception as exc:
            errors.append(f"{trade.pair}: {exc}")

    save_state()  # persist halted state so a restart stays halted
    return {"closed": closed, "errors": errors}


@router.get("/learner-stats")
async def learner_stats():
    """Return the AI learner's current state: win rate, model activation, feature importances."""
    return trade_learner.stats()


@router.post("/learner-reset")
async def learner_reset():
    """Wipe the AI learner's history and model so it relearns from scratch.

    Use after the cross-pair sizing fix: past trades were taken at the wrong
    size, so their outcomes shouldn't bias the model going forward. The learner
    stays ENABLED — it simply starts collecting fresh data from neutral.
    """
    discarded = trade_learner.reset()
    return {
        "status": "reset",
        "discarded_trades": discarded,
        "model_active": False,
        "trades_until_active": trade_learner.MIN_TRADES,
    }


@router.get("/signal")
async def current_signal():
    """Return the current signal for each configured pair WITHOUT placing a trade.

    Useful for diagnosing why trades aren't firing: shows what signal the engine
    is computing, its confidence, and which filter would reject it.
    """
    from datetime import timezone
    from ..intraday import compute_day_signal
    from ..providers import oanda as _oanda
    from .. import pips as pip_module
    from ..autotrader.state import bot_state as _state

    state = _state
    if not state.token or not state.account_id:
        raise HTTPException(400, detail="Bot is not running — start it first to provide credentials.")

    base_cfg = state.config
    now = datetime.now(timezone.utc)
    ema_min = now.hour * 60 + now.minute
    in_london_open = 7 * 60 <= ema_min < 9 * 60 + 30
    in_ny_open = 13 * 60 + 30 <= ema_min < 15 * 60 + 30
    ema_window_open = in_london_open or in_ny_open

    results = []
    for pair in base_cfg.pairs:
        cfg = base_cfg.resolved_for(pair)  # apply per-pair profile
        entry: dict = {"pair": pair, "time_utc": now.strftime("%H:%M"), "filters": []}
        try:
            df = await asyncio.to_thread(
                _oanda.get_candles, pair, state.token, "M5", 100, state.base_url
            )
            if len(df) < 20:
                entry["error"] = f"Only {len(df)} M5 bars returned"
                results.append(entry)
                continue

            sig = compute_day_signal(pair, df)
            entry["signal"] = sig.action
            entry["confidence"] = round(sig.confidence, 1)
            entry["stop_pips"] = sig.stop_pips

            # Report which filters would fire
            if cfg.active_hours_utc and not cfg.in_active_hours(now.hour):
                entry["filters"].append(
                    f"OUTSIDE_ACTIVE_HOURS (now {now.hour:02d} UTC; windows {cfg.active_hours_utc})"
                )
            if cfg.ema_session_window and not ema_window_open:
                entry["filters"].append(
                    f"EMA_WINDOW_CLOSED (now {now.strftime('%H:%M')} UTC; open 07:00-09:30, 13:30-15:30)"
                )
            if sig.action == "DAY_HOLD":
                entry["filters"].append("SIGNAL_IS_HOLD")
            if sig.confidence < cfg.min_confidence * 100:
                entry["filters"].append(
                    f"CONFIDENCE_LOW ({sig.confidence:.0f}% < {cfg.min_confidence * 100:.0f}%)"
                )

            try:
                pricing = await asyncio.to_thread(
                    _oanda.get_pricing, [pair], state.token, state.account_id, state.base_url
                )
                instr = pip_module.normalize(pair)
                spread_pips = float((pricing.get(instr) or {}).get("spread_pips") or 0.0)
                entry["spread_pips"] = round(spread_pips, 2)
                if spread_pips > cfg.max_spread_pips:
                    entry["filters"].append(
                        f"SPREAD_TOO_HIGH ({spread_pips:.1f} pips > max {cfg.max_spread_pips:.1f})"
                    )
            except Exception as exc:
                entry["spread_error"] = str(exc)

            entry["would_trade"] = (
                len(entry["filters"]) == 0
                and sig.action != "DAY_HOLD"
            )
        except Exception as exc:
            entry["error"] = str(exc)
        results.append(entry)

    return {
        "utc_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "ema_window_open": ema_window_open,
        "pairs": results,
    }
