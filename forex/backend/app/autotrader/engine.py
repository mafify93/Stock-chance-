"""Core auto-trader engine.

scan_and_trade() is called on the APScheduler interval (default every 5 min).
It evaluates each configured pair against the intraday signal engine and, when
conditions align, places a bracket order on OANDA with the stop-loss and
take-profit already attached.

Strategy: Intraday momentum + multi-TF trend alignment
─────────────────────────────────────────────────────────
1. Session gate   – only trade during London (07-16 UTC) or NY (12-21 UTC)
2. Account check  – fetch live NAV; apply daily-loss halt if needed
3. Signal eval    – compute_day_signal() on M5 candles + H1 trend candles
4. Filters        – confidence ≥ threshold, spread ≤ max, existing position check
5. Sizing         – fixed-fractional: risk_pct % of NAV ÷ (stop_pips × pip_value)
6. Execution      – OANDA market order with SL/TP bracket; log TradeRecord

The engine never assumes the server is long-running: every cycle is a fresh
OANDA API call. If the server restarts, the in-memory state clears and the bot
is treated as stopped (but OANDA's bracket orders remain on their trades until
hit or the user cancels them from the Positions tab).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import pandas as pd

from .. import pips as pip_module
from ..indicators import average_true_range
from ..intraday import compute_day_signal
from ..providers import oanda
from ..sessions import get_market_session, in_blackout, is_rollover, ny_close_imminent
from ..signals import analyze as swing_analyze
from .calendar import refresh_blackout_windows
from .ict_sweep import ict_session_sweep
from .learner import TradeFeatures, trade_learner
from .london_breakout import london_open_breakout
from .opening_range import opening_range_breakout
from .order_blocks import order_block_reversal
from .silver_bullet import silver_bullet
from .risk import calculate_units
from .state import TradeRecord, bot_state
from . import telegram

# H1 swing score beyond this magnitude counts as a committed trend direction.
H1_TREND_THRESHOLD = 0.15


def h1_blocks_trade(action: str, h1_score: float | None) -> bool:
    """Pure H1 trend filter: block an M5 entry only when it clearly fights the
    H1 trend. Neutral or aligned H1 (or no H1 data) never blocks.

    `action` is "DAY_BUY" / "DAY_SELL"; `h1_score` is signals.analyze().score
    on H1 candles (-1 bearish .. +1 bullish).
    """
    if h1_score is None:
        return False
    if action == "DAY_BUY" and h1_score <= -H1_TREND_THRESHOLD:
        return True
    if action == "DAY_SELL" and h1_score >= H1_TREND_THRESHOLD:
        return True
    return False

log = logging.getLogger(__name__)

# Pairs that tend to move together (positive correlation ~0.70–0.94 on H4).
# We block opening both in the same direction to avoid hidden double-exposure.
# EUR_JPY and GBP_JPY share JPY as the counter-currency (~0.93 corr); taking
# both long simultaneously doubles JPY exposure without proportional extra edge.
POSITIVE_CORR_PAIRS: list[tuple[str, str]] = [
    ("EUR_USD", "GBP_USD"),
    ("EUR_USD", "AUD_USD"),
    ("GBP_USD", "AUD_USD"),
    ("EUR_JPY", "GBP_JPY"),
]


def _correlation_allows(pair: str, is_buy: bool, open_trades: list) -> bool:
    """Return False if taking this trade would create correlated exposure."""
    open_dir = {t.pair: (t.side == "long") for t in open_trades}
    for a, b in POSITIVE_CORR_PAIRS:
        other = b if pair == a else (a if pair == b else None)
        if other and other in open_dir and open_dir[other] == is_buy:
            log.debug(
                f"AutoTrader {pair}: correlated exposure with {other} "
                f"(both {'long' if is_buy else 'short'}), skipping"
            )
            return False
    return True


async def monitor_open_trades() -> None:
    """Trade management: partial TP, break-even stop, time exit, session flatten."""
    state = bot_state
    if not state.running or not state.token:
        return

    now = datetime.now(timezone.utc)

    # Flatten all positions ~5 minutes before the 17:00 ET NY session close.
    # DST-aware (20:55 UTC in summer, 21:55 UTC in winter).
    if state.config.session_filter and ny_close_imminent(now):
        # Send daily summary before closing positions so P&L reflects open trades.
        if state.start_of_day_balance:
            telegram.notify_daily_summary(
                state.daily_pl, state.trades_today, state.start_of_day_balance
            )
        open_trades = state.open_trades
        if open_trades:
            log.info("AutoTrader: end-of-session flatten — closing all positions before NY close")
            for trade in list(open_trades):
                try:
                    await asyncio.to_thread(
                        oanda.close_position,
                        state.token,
                        state.account_id,
                        trade.pair,
                        trade.side,
                        state.base_url,
                    )
                    # Fetch realized P&L so daily accounting and McKay step-down stay accurate.
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
                        trade.closed_at = now.isoformat()
                        trade.realized_pl = realized_pl
                        state.daily_pl += realized_pl
                        if realized_pl < 0:
                            state.consecutive_losses += 1
                        elif realized_pl > 0:
                            state.consecutive_losses = 0
                    log.info(
                        f"AutoTrader: end-of-session closed {trade.pair} ({trade.side}) "
                        f"P&L {realized_pl:+.2f}"
                    )
                    telegram.notify_trade_close(trade.pair, trade.side, realized_pl)
                except Exception as exc:
                    log.warning(f"AutoTrader: end-of-session close failed for {trade.pair}: {exc}")
        return

    for trade in list(state.open_trades):
        try:
            await _manage_trade(trade, now)
        except Exception as exc:
            log.debug(f"AutoTrader trade management {trade.pair}: {exc}")


async def _manage_trade(trade, now: datetime) -> None:
    """Per-trade management: partial TP at 1R, break-even stop, time-decay stop.

    "R" (the unit of risk used for profit targets) is anchored to the trade's
    ORIGINAL stop distance via trade.init_risk, so moving the live stop — for
    break-even or time-decay — never shifts where the 1R profit trigger sits.
    """
    state = bot_state
    cfg = state.config
    is_long = trade.side == "long"
    risk = trade.init_risk or abs(trade.entry - trade.stop)

    if risk <= 0:
        return

    # Fetch current mid price — shared by all checks below.
    try:
        pricing = await asyncio.to_thread(
            oanda.get_pricing,
            [trade.pair],
            state.token,
            state.account_id,
            state.base_url,
        )
        instr = pip_module.normalize(trade.pair)
        mid = (pricing.get(instr) or {}).get("mid")
        if not mid:
            return
    except Exception:
        return

    mid = float(mid)
    profit = (mid - trade.entry) if is_long else (trade.entry - mid)
    profit_pips = pip_module.to_pips(trade.pair, profit)

    # ── Time-decay stop: tighten (never market-close) a stale, losing trade ──
    # Your call: don't guillotine a trade that might recover. Give it full room
    # early, then a progressively shorter leash as it ages while still red. It
    # keeps its comeback chance but bleeds less if it keeps going. Once a trade
    # reaches +1R (partial_closed) the break-even logic below owns the stop.
    try:
        opened = datetime.fromisoformat(trade.opened_at.replace("Z", "+00:00"))
        hours_open = (now - opened).total_seconds() / 3600
    except Exception:
        hours_open = 0.0

    if (
        cfg.time_decay_stop
        and cfg.max_trade_hours > 0
        and profit < 0
        and not trade.partial_closed
    ):
        decay_start = cfg.max_trade_hours * 0.5  # full room until half the window
        if hours_open >= decay_start:
            span = max(cfg.max_trade_hours - decay_start, 1e-9)
            progress = min(1.0, (hours_open - decay_start) / span)
            min_risk_frac = 0.25  # never tighten below 25% of the original risk
            allowed_frac = 1.0 - progress * (1.0 - min_risk_frac)
            allowed_risk = risk * allowed_frac
            decayed_sl = (trade.entry - allowed_risk) if is_long else (trade.entry + allowed_risk)
            tighter = (decayed_sl > trade.stop) if is_long else (decayed_sl < trade.stop)
            if tighter:
                try:
                    await asyncio.to_thread(
                        oanda.update_trade_stop_loss,
                        state.token, state.account_id, trade.trade_id,
                        decayed_sl, trade.pair, state.base_url,
                    )
                    with state._lock:
                        trade.stop = decayed_sl
                    log.info(
                        f"AutoTrader {trade.pair}: time-decay stop → {decayed_sl:.5f} "
                        f"({allowed_frac:.0%} of original risk, {hours_open:.1f}h open, "
                        f"{profit_pips:+.1f} pips)"
                    )
                except Exception as exc:
                    log.warning(f"AutoTrader {trade.pair}: time-decay tighten failed: {exc}")

    # ── High-water mark tracking ─────────────────────────────────────────────
    # Always update the peak profit so we know how far in our favour the trade got.
    current_r = profit / risk if risk > 0 else 0.0
    if current_r > trade.peak_profit_r:
        with state._lock:
            trade.peak_profit_r = current_r

    # ── HWM close: sell the moment we fall back to entry after being in profit ─
    # If the trade reached hwm_r × risk in profit (default 0.2R = 20% of stop)
    # and is now back at or below entry, close it immediately rather than letting
    # it ride to the original SL. This catches the scenario: "was making money,
    # market reversed, now about to go negative — get out now."
    # Only fires below the 0.5R breakeven level; above that OANDA's own moved
    # stop handles it automatically.
    if (
        cfg.hwm_close
        and not trade.breakeven_set      # OANDA stop not yet at entry
        and trade.peak_profit_r >= cfg.hwm_r   # was meaningfully in profit
        and profit <= 0                  # now back at or below entry
    ):
        try:
            close_resp = await asyncio.to_thread(
                oanda.close_trade,
                state.token, state.account_id, trade.trade_id, state.base_url,
            )
            # Extract actual P&L from the fill response instead of hardcoding 0.
            fill = close_resp.get("orderFillTransaction") or {}
            closed_legs = fill.get("tradesClosed") or []
            actual_pl = sum(float(leg.get("realizedPL") or 0) for leg in closed_legs)
            with state._lock:
                trade.status = "closed"
                trade.closed_at = now.isoformat()
                trade.realized_pl = actual_pl
                state.daily_pl += actual_pl
                if actual_pl < 0:
                    state.consecutive_losses += 1
                elif actual_pl > 0:
                    state.consecutive_losses = 0
            log.info(
                f"AutoTrader {trade.pair}: HWM close — peaked at "
                f"+{trade.peak_profit_r:.2f}R ({profit_pips:+.1f}p), "
                f"fell back to entry; P&L {actual_pl:+.2f}"
            )
            telegram.notify_trade_close(trade.pair, trade.side, actual_pl)
        except Exception as exc:
            log.warning(f"AutoTrader {trade.pair}: HWM close failed: {exc}")
        return

    # ── Early breakeven: eliminate the "giving back profit" problem ──────────
    # Move SL to entry + 1 pip as soon as profit reaches either:
    #   (a) breakeven_r × risk  (R-based, default 0.25R)
    #   (b) profit_lock_pips    (pip-based floor, default 5 pips)
    # Whichever fires first — with a hard 3-pip noise floor so a 1-pip wick
    # never triggers it. Two separate threshold paths so trades with large stops
    # don't have to wait for an enormous pip move, and trades with small stops
    # don't get stopped out on noise.
    if cfg.breakeven_stop and not trade.breakeven_set:
        be_trigger_r = risk * cfg.breakeven_r
        be_trigger_pips_price = pip_module.from_pips(trade.pair, cfg.profit_lock_pips)
        be_trigger = min(be_trigger_r, be_trigger_pips_price)
        if profit >= be_trigger and profit_pips >= 3.0:
            buf = pip_module.from_pips(trade.pair, 1.0)
            be_sl = (trade.entry + buf) if is_long else (trade.entry - buf)
            should_move = (be_sl > trade.stop) if is_long else (be_sl < trade.stop)
            if should_move:
                try:
                    await asyncio.to_thread(
                        oanda.update_trade_stop_loss,
                        state.token, state.account_id, trade.trade_id,
                        be_sl, trade.pair, state.base_url,
                    )
                    with state._lock:
                        trade.stop = be_sl
                        trade.breakeven_set = True
                    log.info(
                        f"AutoTrader {trade.pair}: breakeven lock at "
                        f"{be_sl:.5f} ({profit_pips:+.1f}p, "
                        f"{profit/risk:.1f}R in profit)"
                    )
                except Exception as exc:
                    log.warning(f"AutoTrader {trade.pair}: breakeven move failed: {exc}")

    # Past here we only act when the trade is at or beyond 1R profit.
    if profit < risk:
        return

    # ── Partial TP: close 50% of units at 1R profit ──────────────────────────
    if cfg.partial_tp and not trade.partial_closed:
        half = max(1, trade.units // 2)
        try:
            await asyncio.to_thread(
                oanda.close_trade_partial,
                state.token,
                state.account_id,
                trade.trade_id,
                half,
                state.base_url,
            )
            with state._lock:
                trade.units -= half
                trade.partial_closed = True
            log.info(
                f"AutoTrader {trade.pair}: partial TP — closed {half:,} units at "
                f"+{profit_pips:.1f} pips; {trade.units:,} units still running"
            )
        except Exception as exc:
            log.warning(f"AutoTrader {trade.pair}: partial TP failed: {exc}")

    # ── Runner management: trail the remaining units, floored at break-even ──
    # The break-even floor guarantees a risk-free runner after the partial; the
    # ATR (Chandelier-style) trail lets a winner run past 2R instead of parking
    # at entry. The original 2R take-profit order stays attached on OANDA, so the
    # runner exits at whichever comes first — trail or limit (the hybrid the
    # research found optimal). Falls back to a plain break-even move if trailing
    # is disabled or the ATR can't be computed.
    if not (cfg.breakeven_stop or cfg.trail_runner):
        return

    buffer = pip_module.from_pips(trade.pair, 1.0)
    be_sl = (trade.entry + buffer) if is_long else (trade.entry - buffer)
    target_sl = be_sl

    if cfg.trail_runner:
        try:
            df = await asyncio.to_thread(
                oanda.get_candles, trade.pair, state.token, "M5", 100, state.base_url
            )
            atr = float(average_true_range(df, cfg.trail_atr_period).iloc[-1])
            if not (atr > 0):
                raise ValueError("ATR unavailable")
            entry_dt = datetime.fromisoformat(trade.opened_at.replace("Z", "+00:00"))
            since = df[df.index >= entry_dt]
            if len(since) == 0:
                since = df.tail(1)
            if is_long:
                chandelier = float(since["High"].max()) - cfg.trail_atr_mult * atr
                target_sl = max(be_sl, chandelier)
            else:
                chandelier = float(since["Low"].min()) + cfg.trail_atr_mult * atr
                target_sl = min(be_sl, chandelier)
        except Exception as exc:
            log.debug(f"AutoTrader {trade.pair}: ATR trail calc failed, using BE: {exc}")
            target_sl = be_sl

    # Only ever move the stop in the favourable direction.
    if is_long and target_sl <= trade.stop:
        return
    if not is_long and target_sl >= trade.stop:
        return

    try:
        await asyncio.to_thread(
            oanda.update_trade_stop_loss,
            state.token,
            state.account_id,
            trade.trade_id,
            target_sl,
            trade.pair,
            state.base_url,
        )
        with state._lock:
            trade.stop = target_sl
        log.info(f"AutoTrader {trade.pair}: stop trailed to {target_sl:.5f}")
    except Exception as exc:
        log.warning(f"AutoTrader {trade.pair}: trail/BE move failed: {exc}")


async def resync_open_trades() -> None:
    """Pull live open trades from OANDA into bot_state on bot start.

    This is the fix for the restart-amnesia bug: when the Render service
    restarts, in-memory state is wiped. Without this, the bot forgets all
    positions it previously opened, causing the max_positions and daily-loss
    guards to reset to zero even though OANDA still holds those trades.

    Called once from the /start endpoint. It re-populates open_trades with
    whatever OANDA reports, so guards stay accurate across restarts.
    """
    state = bot_state
    if not state.token or not state.account_id:
        return

    try:
        live_trades = await asyncio.to_thread(
            oanda.get_open_trades, state.token, state.account_id, state.base_url
        )
    except Exception as exc:
        log.warning(f"AutoTrader: resync failed (non-fatal): {exc}")
        return

    known_ids = {t.trade_id for t in state.trades}
    recovered = 0
    for t in live_trades:
        trade_id = str(t.get("id", ""))
        if not trade_id or trade_id in known_ids:
            continue
        instr = t.get("instrument", "")
        current_units = int(t.get("currentUnits", 0))
        if current_units == 0:
            continue
        side = "long" if current_units > 0 else "short"
        entry = float(t.get("price", 0))
        sl_order = t.get("stopLossOrder") or {}
        tp_order = t.get("takeProfitOrder") or {}
        sl_price = float(sl_order.get("price", 0))
        record = TradeRecord(
            pair=instr,
            side=side,
            units=abs(current_units),
            entry=entry,
            stop=sl_price,
            target=float(tp_order.get("price", 0)),
            opened_at=t.get("openTime", datetime.now(timezone.utc).isoformat()),
            trade_id=trade_id,
            init_risk=abs(entry - sl_price) if sl_price else 0.0,
        )
        with state._lock:
            state.trades.append(record)
        recovered += 1

    if recovered:
        log.info(f"AutoTrader: recovered {recovered} open trade(s) from OANDA after restart")


async def sync_closed_trades() -> None:
    """Detect which bot trades have been closed by OANDA (SL/TP hit) and update
    daily P&L and the McKay consecutive-loss step-down scale.

    Called at the start of every scan cycle so the bot knows about fills that
    happened between scans without needing a webhook.
    """
    state = bot_state
    if not state.running or not state.token or not state.open_trades:
        return

    try:
        live_trades = await asyncio.to_thread(
            oanda.get_open_trades, state.token, state.account_id, state.base_url
        )
    except Exception as exc:
        log.debug(f"AutoTrader: trade sync error: {exc}")
        return

    live_ids = {str(t.get("id")) for t in live_trades}

    for trade in list(state.open_trades):
        if trade.trade_id in live_ids:
            continue  # still open

        # Fetch the realized P&L from OANDA so daily accounting stays accurate.
        realized_pl = 0.0
        try:
            trade_data = await asyncio.to_thread(
                oanda.get_trade, state.token, state.account_id, trade.trade_id, state.base_url
            )
            realized_pl = float(trade_data.get("realizedPL") or 0)
        except Exception as exc:
            log.debug(f"AutoTrader: could not fetch P&L for trade {trade.trade_id}: {exc}")

        with state._lock:
            trade.status = "closed"
            trade.closed_at = datetime.now(timezone.utc).isoformat()
            trade.realized_pl = realized_pl
            state.daily_pl += realized_pl
            if realized_pl < 0:
                state.consecutive_losses += 1
            elif realized_pl > 0:
                state.consecutive_losses = 0
            # Scratch trades (BE stop hit) don't reset or increment the streak.

        # Feed outcome to the AI learner so it can improve future entry decisions.
        if trade.entry_features:
            try:
                features = TradeFeatures.from_dict(trade.entry_features)
                trade_learner.record(features, realized_pl)
            except Exception as exc:
                log.debug(f"AutoTrader: learner.record failed for {trade.pair}: {exc}")

        outcome = "win" if realized_pl > 0 else ("loss" if realized_pl < 0 else "scratch")
        log.info(
            f"AutoTrader {trade.pair} ({trade.side}): closed — "
            f"realizedPL {realized_pl:+.2f} [{outcome}], "
            f"daily P&L {state.daily_pl:+.2f}, "
            f"consecutive losses: {state.consecutive_losses}"
        )
        telegram.notify_trade_close(trade.pair, trade.side, realized_pl)

    # McKay step-down: recalculate risk_scale from consecutive_losses
    cl = state.consecutive_losses
    if cl == 0:
        new_scale = 1.0
    elif cl == 1:
        new_scale = 0.75
    elif cl >= 2:
        new_scale = 0.50
    else:
        new_scale = 1.0

    if new_scale != state.risk_scale:
        with state._lock:
            state.risk_scale = new_scale
        log.info(f"AutoTrader: risk scale set to {new_scale:.0%} "
                 f"(consecutive losses: {cl})")


async def scan_and_trade() -> None:
    """One scan cycle: evaluate all configured pairs and enter where warranted."""
    state = bot_state

    if not state.running or state.halted:
        return

    # Reconcile closed trades first so guards below are accurate.
    await sync_closed_trades()

    if not state.token or not state.account_id:
        log.warning("AutoTrader: no credentials, scan skipped")
        return

    now = datetime.now(timezone.utc)
    cfg = state.config

    # ── Session gate ─────────────────────────────────────────────────────────
    if cfg.session_filter:
        session = get_market_session(now)
        if session.status != "open":
            return
        if not (set(session.active_sessions) & {"London", "New York"}):
            log.debug("AutoTrader: outside London/NY session, scan skipped")
            return

    # ── Rollover & news blackout gates (no new entries) ──────────────────────
    if cfg.block_rollover and is_rollover(now):
        log.debug("AutoTrader: interbank rollover window, no new entries")
        return
    if in_blackout(now, cfg.news_blackout_utc):
        log.debug("AutoTrader: news blackout window, no new entries")
        return

    # ── Account summary ───────────────────────────────────────────────────────
    try:
        account_raw = await asyncio.to_thread(
            oanda.get_account_summary, state.token, state.account_id, state.base_url
        )
    except Exception as exc:
        log.error(f"AutoTrader: account fetch failed: {exc}")
        return

    nav = float(account_raw.get("NAV") or account_raw.get("balance") or 0)
    if nav <= 0:
        log.warning("AutoTrader: NAV is zero or missing")
        return

    # Convert NAV to USD for position sizing — pip_value_per_unit() returns
    # USD values, so we need the USD-equivalent NAV regardless of account currency.
    account_currency = account_raw.get("currency", "USD")
    nav_usd = nav
    if account_currency != "USD":
        fx_pair = f"USD_{account_currency}"
        try:
            fx_pricing = await asyncio.to_thread(
                oanda.get_pricing, [fx_pair], state.token, state.account_id, state.base_url
            )
            fx_mid = (fx_pricing.get(pip_module.normalize(fx_pair)) or {}).get("mid")
            if fx_mid and float(fx_mid) > 0:
                nav_usd = nav / float(fx_mid)
                log.debug(
                    f"AutoTrader: {account_currency} account, NAV {nav:.0f} "
                    f"→ {nav_usd:.0f} USD (USD/{account_currency} {float(fx_mid):.4f})"
                )
        except Exception as exc:
            log.debug(f"AutoTrader: {fx_pair} rate unavailable, sizing in account currency: {exc}")

    # ── Daily reset & loss-limit check ───────────────────────────────────────
    today = now.date()
    needs_calendar_refresh = False
    with state._lock:
        if state.session_date != today:
            state.session_date = today
            state.start_of_day_balance = nav
            state.daily_pl = 0.0
            state.trades_today = 0
            state.halted = False
            state.halt_reason = ""
            needs_calendar_refresh = True

    # Refresh outside the lock via a thread so the blocking HTTP call doesn't
    # freeze the asyncio event loop for up to 10 seconds once per trading day.
    if needs_calendar_refresh:
        await asyncio.to_thread(refresh_blackout_windows, cfg)

    # ── Daily loss circuit-breaker ────────────────────────────────────────────
    if (
        cfg.daily_loss_halt_pct > 0
        and state.start_of_day_balance
        and state.start_of_day_balance > 0
        and state.daily_pl / state.start_of_day_balance <= -cfg.daily_loss_halt_pct
    ):
        log.info(
            f"AutoTrader: daily loss circuit-breaker — P&L {state.daily_pl:+.2f} "
            f"({state.daily_pl / state.start_of_day_balance:.1%} of SOD balance), "
            f"no new entries today"
        )
        return

    # ── Trade-count guards ────────────────────────────────────────────────────
    if state.trades_today >= cfg.max_trades_per_day:
        log.debug("AutoTrader: daily trade cap reached")
        return

    if len(state.open_trades) >= cfg.max_positions:
        log.debug("AutoTrader: max concurrent positions reached")
        return

    open_pairs = {t.pair for t in state.open_trades}

    # ── Pair scan ─────────────────────────────────────────────────────────────
    for pair in cfg.pairs:
        if len(state.open_trades) >= cfg.max_positions:
            break
        if state.trades_today >= cfg.max_trades_per_day:
            break
        if pair in open_pairs:
            continue

        try:
            await _evaluate_pair(pair, nav_usd, now)
        except Exception as exc:
            log.error(f"AutoTrader: unexpected error on {pair}: {exc}")


async def _evaluate_pair(pair: str, nav: float, now: datetime) -> None:
    """Evaluate one pair and place a trade if all conditions are met."""
    state = bot_state
    cfg = state.config

    # ── M5 candles ───────────────────────────────────────────────────────────
    try:
        df_m5 = await asyncio.to_thread(
            oanda.get_candles, pair, state.token, "M5", 100, state.base_url
        )
    except Exception as exc:
        log.debug(f"AutoTrader {pair}: M5 candles error: {exc}")
        return

    if len(df_m5) < 20:
        log.debug(f"AutoTrader {pair}: insufficient M5 data ({len(df_m5)} bars)")
        return

    # ── Signal selection: London Breakout (preferred) or EMA/VWAP/RSI ─────────
    # London Breakout has a better-documented edge at London open (07:00–10:00
    # UTC). Outside that window, or for pairs not in london_breakout_pairs, we
    # fall back to the existing intraday momentum signal.
    signal_type = "ema_vwap_rsi"
    day_sig = None

    if cfg.use_london_breakout and pair in cfg.london_breakout_pairs:
        try:
            # Fetch more history (200 bars ≈ 16 h) to capture the full Asian session
            df_m5_long = await asyncio.to_thread(
                oanda.get_candles, pair, state.token, "M5", 200, state.base_url
            )
            lb_sig = london_open_breakout(pair, df_m5_long, now)
            if lb_sig is not None:
                day_sig = lb_sig
                signal_type = "london_breakout"
                log.debug(
                    f"AutoTrader {pair}: using London Open Breakout signal "
                    f"({day_sig.action}, conf={day_sig.confidence:.0f}%)"
                )
        except Exception as exc:
            log.debug(f"AutoTrader {pair}: London Breakout error (falling back): {exc}")

    # Fetch shared M1 bars once for all M1-based ICT strategies (750 bars ≈ 12.5 h).
    # Reused by ICT Sweep, ORB, and Silver Bullet so we avoid triple API calls.
    df_m1: pd.DataFrame | None = None
    _m1_needed = (
        (cfg.use_ict_sweep or cfg.use_orb or cfg.use_silver_bullet)
        and day_sig is None
    )
    if _m1_needed:
        try:
            df_m1 = await asyncio.to_thread(
                oanda.get_candles, pair, state.token, "M1", 750, state.base_url
            )
        except Exception as exc:
            log.debug(f"AutoTrader {pair}: M1 fetch error: {exc}")

    # ICT Session Sweep: NY 9am setup (13:00–15:00 UTC)
    if day_sig is None and cfg.use_ict_sweep and df_m1 is not None:
        try:
            ict_sig = ict_session_sweep(pair, df_m1, now)
            if ict_sig is not None:
                day_sig = ict_sig
                signal_type = "ict_sweep"
                log.debug(
                    f"AutoTrader {pair}: ICT Session Sweep "
                    f"({day_sig.action}, conf={day_sig.confidence:.0f}%)"
                )
        except Exception as exc:
            log.debug(f"AutoTrader {pair}: ICT Sweep error (falling back): {exc}")

    # Opening Range Breakout: NY first-15-min range (13:15–17:00 UTC)
    if day_sig is None and cfg.use_orb and df_m1 is not None:
        try:
            orb_sig = opening_range_breakout(pair, df_m1, now)
            if orb_sig is not None:
                day_sig = orb_sig
                signal_type = "orb"
                log.debug(
                    f"AutoTrader {pair}: ORB Breakout "
                    f"({day_sig.action}, conf={day_sig.confidence:.0f}%)"
                )
        except Exception as exc:
            log.debug(f"AutoTrader {pair}: ORB error (falling back): {exc}")

    # ICT Silver Bullet: FVG entries at 07:00, 14:00, 18:00 UTC windows
    if day_sig is None and cfg.use_silver_bullet and df_m1 is not None:
        try:
            sb_sig = silver_bullet(pair, df_m1, now)
            if sb_sig is not None:
                day_sig = sb_sig
                signal_type = "silver_bullet"
                log.debug(
                    f"AutoTrader {pair}: Silver Bullet FVG "
                    f"({day_sig.action}, conf={day_sig.confidence:.0f}%)"
                )
        except Exception as exc:
            log.debug(f"AutoTrader {pair}: Silver Bullet error (falling back): {exc}")

    # Order Block Reversal: M15 structural OB zones
    if day_sig is None and cfg.use_order_blocks:
        try:
            df_m15 = await asyncio.to_thread(
                oanda.get_candles, pair, state.token, "M15", 60, state.base_url
            )
            ob_sig = order_block_reversal(pair, df_m15, now)
            if ob_sig is not None:
                day_sig = ob_sig
                signal_type = "order_block"
                log.debug(
                    f"AutoTrader {pair}: Order Block Reversal "
                    f"({day_sig.action}, conf={day_sig.confidence:.0f}%)"
                )
        except Exception as exc:
            log.debug(f"AutoTrader {pair}: Order Block error (falling back): {exc}")

    if day_sig is None:
        if not cfg.use_ema_fallback:
            return  # EMA fallback disabled — ICT strategies only

        # EMA session window: restrict fallback to genuine momentum windows only.
        if cfg.ema_session_window:
            ema_min = now.hour * 60 + now.minute
            in_london_open = 7 * 60 <= ema_min < 9 * 60 + 30
            in_ny_open = 13 * 60 + 30 <= ema_min < 15 * 60 + 30
            if not (in_london_open or in_ny_open):
                return

        # Hard time gate (off by default — too broad, removes good trades).
        if cfg.block_ema_ny_open and 13 <= now.hour < 17:
            return
        # Fall back to EMA/VWAP/RSI intraday signal
        try:
            day_sig = compute_day_signal(pair, df_m5)
        except Exception as exc:
            log.debug(f"AutoTrader {pair}: signal error: {exc}")
            return

        # ATR expansion filter extended to EMA during NY open (13:00–16:00 UTC).
        if cfg.use_atr_expansion_filter and 13 <= now.hour < 16:
            try:
                atr_series_live = average_true_range(df_m5, 14)
                if len(atr_series_live) > cfg.atr_expansion_lookback:
                    atr_val = float(atr_series_live.iloc[-1])
                    atr_mean = float(atr_series_live.iloc[-cfg.atr_expansion_lookback - 1:-1].mean())
                    if atr_mean > 0 and atr_val < atr_mean * 0.8:
                        log.debug(f"AutoTrader {pair}: EMA suppressed — ATR contracting at NY open "
                                  f"({atr_val:.6f} < 80% of {atr_mean:.6f})")
                        return
            except Exception as exc:
                log.debug(f"AutoTrader {pair}: ATR NY-open check failed (non-fatal): {exc}")

        # NY open momentum alignment (13:00–16:00 UTC).
        # EMA's midnight VWAP carries the London session's directional bias into NY open.
        # Gate EMA entries to only fire when price confirms the actual NY session direction
        # — i.e. price vs. the first 13:00 UTC bar's open.
        if cfg.use_ny_open_momentum_filter and 13 <= now.hour < 16:
            try:
                today_ny_start = now.replace(hour=13, minute=0, second=0, microsecond=0)
                idx = df_m5.index
                if idx.tzinfo is None and today_ny_start.tzinfo is not None:
                    today_ny_start = today_ny_start.replace(tzinfo=None)
                ny_bars = df_m5[df_m5.index >= pd.Timestamp(today_ny_start)]
                if len(ny_bars) > 0:
                    ny_open_ref = float(ny_bars["Open"].iloc[0])
                    cur = float(df_m5["Close"].iloc[-1])
                    if day_sig.action == "DAY_BUY" and cur <= ny_open_ref:
                        log.debug(f"AutoTrader {pair}: EMA BUY suppressed — NY session bearish "
                                  f"({cur:.5f} ≤ NY open {ny_open_ref:.5f})")
                        return
                    if day_sig.action == "DAY_SELL" and cur >= ny_open_ref:
                        log.debug(f"AutoTrader {pair}: EMA SELL suppressed — NY session bullish "
                                  f"({cur:.5f} ≥ NY open {ny_open_ref:.5f})")
                        return
            except Exception as exc:
                log.debug(f"AutoTrader {pair}: NY momentum filter failed (non-fatal): {exc}")

    if day_sig.action == "DAY_HOLD":
        with state._lock:
            state.pending_signals.pop(pair, None)
        return

    # ── Signal confirmation (EMA signal only — London Breakout is self-confirming)
    if cfg.signal_confirmation and signal_type == "ema_vwap_rsi":
        prev = state.pending_signals.get(pair)
        with state._lock:
            state.pending_signals[pair] = day_sig.action
        if prev != day_sig.action:
            log.debug(
                f"AutoTrader {pair}: {day_sig.action} — waiting for confirmation "
                f"(previous: {prev or 'none'})"
            )
            return
        with state._lock:
            state.pending_signals.pop(pair, None)

    # ── H1 trend filter ───────────────────────────────────────────────────────
    if cfg.h1_trend_filter:
        try:
            df_h1 = await asyncio.to_thread(
                oanda.get_candles, pair, state.token, "H1", 250, state.base_url
            )
            if len(df_h1) >= 50:
                h1_score = swing_analyze(pair, df_h1).score
                if h1_blocks_trade(day_sig.action, h1_score):
                    log.debug(
                        f"AutoTrader {pair}: {day_sig.action} blocked — "
                        f"fights H1 trend (h1_score {h1_score:+.2f})"
                    )
                    return
        except Exception as exc:
            log.debug(f"AutoTrader {pair}: H1 filter error (non-fatal): {exc}")

    # ── Spread check ─────────────────────────────────────────────────────────
    spread_pips = 0.0
    try:
        pricing = await asyncio.to_thread(
            oanda.get_pricing,
            [pair],
            state.token,
            state.account_id,
            state.base_url,
        )
        instr = pip_module.normalize(pair)
        spread_pips = float((pricing.get(instr) or {}).get("spread_pips") or 0.0)
        if spread_pips > cfg.max_spread_pips:
            log.debug(f"AutoTrader {pair}: spread {spread_pips:.1f} pips > max {cfg.max_spread_pips}")
            return
    except Exception:
        pass

    # ── ATR (used by learner features and for logging) ────────────────────────
    atr_pips = 0.0
    try:
        atr_series = average_true_range(df_m5, 14)
        if not atr_series.empty:
            atr_pips = round(pip_module.to_pips(pair, float(atr_series.iloc[-1])), 1)
    except Exception:
        pass

    # ── AI Learner: adjust confidence based on historical win rate ────────────
    raw_stop_for_features = day_sig.stop_pips or 0.0
    entry_features = TradeFeatures(
        pair=pair,
        side="long" if day_sig.action == "DAY_BUY" else "short",
        confidence=day_sig.confidence,
        stop_pips=raw_stop_for_features,
        spread_pips=spread_pips,
        atr_pips=atr_pips,
        hour_utc=now.hour,
        signal_type=signal_type,
    )

    if cfg.use_ai_learner:
        multiplier = trade_learner.confidence_multiplier(entry_features)
        win_prob = (multiplier - 0.4) / 1.2  # invert the multiplier formula
        adjusted_confidence = day_sig.confidence * multiplier
        if win_prob < cfg.ai_min_win_prob:
            log.debug(
                f"AutoTrader {pair}: AI learner suppressed entry — "
                f"estimated win prob {win_prob:.0%} < min {cfg.ai_min_win_prob:.0%}"
            )
            return
        if multiplier != 1.0:
            log.debug(
                f"AutoTrader {pair}: AI learner adjusted confidence "
                f"{day_sig.confidence:.0f}% → {adjusted_confidence:.0f}% "
                f"(win_prob estimate: {win_prob:.0%})"
            )
        day_sig = type(day_sig)(  # shallow copy with adjusted confidence
            **{**day_sig.__dict__, "confidence": adjusted_confidence}
        )

    # ── Confidence gate ───────────────────────────────────────────────────────
    if day_sig.confidence < cfg.min_confidence * 100:
        log.debug(
            f"AutoTrader {pair}: confidence {day_sig.confidence:.0f}% < "
            f"threshold {cfg.min_confidence * 100:.0f}%"
        )
        return

    # ── Correlation gate ─────────────────────────────────────────────────────
    is_buy = day_sig.action == "DAY_BUY"
    if not _correlation_allows(pair, is_buy, state.open_trades):
        return

    # ── Stop distance ─────────────────────────────────────────────────────────
    raw_stop = day_sig.stop_pips
    if raw_stop is None or raw_stop <= 0:
        return
    stop_pips = max(cfg.min_stop_pips, min(cfg.max_stop_pips, raw_stop))

    # ── Position sizing (McKay step-down applied) ─────────────────────────────
    spot = day_sig.price
    effective_risk = cfg.risk_pct * state.risk_scale
    units = calculate_units(nav, effective_risk, stop_pips, pair, spot)
    if units < 1:
        log.debug(f"AutoTrader {pair}: unit count rounded to 0, skipping")
        return

    # ── Prices ────────────────────────────────────────────────────────────────
    entry = day_sig.entry or day_sig.price

    # Always derive stop from the CLAMPED stop_pips so min_stop_pips is honoured.
    # Using day_sig.stop directly would bypass the clamp and let strategies with
    # tight natural stops (e.g. 5-pip ORB setups) place stops that market noise
    # hits immediately — causing the bot to burn through the daily trade cap.
    delta_sl = pip_module.from_pips(pair, stop_pips)
    stop_price = (entry - delta_sl) if is_buy else (entry + delta_sl)

    # Use the signal's pre-computed target when it delivers at least cfg.rr_ratio
    # reward relative to the (clamped) stop; otherwise use the RR-derived target.
    target_pips = stop_pips * cfg.rr_ratio
    delta_tp = pip_module.from_pips(pair, target_pips)
    rr_target = (entry + delta_tp) if is_buy else (entry - delta_tp)

    if day_sig.target is not None:
        natural_rr = pip_module.to_pips(pair, abs(day_sig.target - entry)) / stop_pips
        target_price = day_sig.target if natural_rr >= cfg.rr_ratio else rr_target
    else:
        target_price = rr_target

    order_units = units if is_buy else -units

    log.info(
        f"AutoTrader: {day_sig.action} {pair} [{signal_type}] "
        f"{order_units:+,} units @ ~{entry:.5f}  "
        f"SL={stop_price:.5f}  TP={target_price:.5f}  "
        f"stop={stop_pips:.1f}pips  conf={day_sig.confidence:.0f}%"
    )

    # ── Place order ───────────────────────────────────────────────────────────
    try:
        result = await asyncio.to_thread(
            oanda.place_market_order,
            state.token,
            state.account_id,
            pair,
            order_units,
            state.base_url,
            stop_price,
            target_price,
        )
    except oanda.OandaError as exc:
        log.error(f"AutoTrader {pair}: OANDA order failed ({exc.status_code}): {exc}")
        return

    # Extract OANDA trade ID from the fill response
    trade_id = "unknown"
    fill_tx = result.get("orderFillTransaction") or {}
    opened = fill_tx.get("tradeOpened") or {}
    if opened.get("tradeID"):
        trade_id = str(opened["tradeID"])
    elif result.get("lastTransactionID"):
        trade_id = str(result["lastTransactionID"])

    record = TradeRecord(
        pair=pair,
        side="long" if is_buy else "short",
        units=abs(units),
        entry=entry,
        stop=stop_price,
        target=target_price,
        opened_at=now.isoformat(),
        trade_id=trade_id,
        init_risk=abs(entry - stop_price),
        entry_features=entry_features.to_dict(),  # stored for learner feedback on close
    )

    with state._lock:
        state.trades.append(record)
        state.trades_today += 1

    log.info(f"AutoTrader {pair}: order placed, trade_id={trade_id}")
    telegram.notify_trade_entry(
        pair, record.side, record.units, entry, stop_price, target_price,
        signal_type, day_sig.confidence,
    )
