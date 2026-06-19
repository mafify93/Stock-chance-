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

from .. import pips as pip_module
from ..intraday import compute_day_signal
from ..providers import oanda
from ..sessions import get_market_session
from .risk import calculate_units
from .state import TradeRecord, bot_state

log = logging.getLogger(__name__)

# Pairs that tend to move together (positive correlation ~0.70–0.94 on H4).
# We block opening both in the same direction to avoid hidden double-exposure.
POSITIVE_CORR_PAIRS: list[tuple[str, str]] = [
    ("EUR_USD", "GBP_USD"),
    ("EUR_USD", "AUD_USD"),
    ("GBP_USD", "AUD_USD"),
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
    """Move stop-loss to break-even on trades at 1R profit; flatten before session end."""
    state = bot_state
    if not state.running or not state.token:
        return

    now = datetime.now(timezone.utc)

    # Flatten all positions 5 minutes before NY session closes (20:55 UTC).
    # This prevents holding through the overnight gap when liquidity is thin
    # and stops can slip significantly.
    if state.config.session_filter and now.hour == 20 and now.minute >= 55:
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
                    with state._lock:
                        trade.status = "closed"
                        trade.closed_at = now.isoformat()
                    log.info(f"AutoTrader: end-of-session closed {trade.pair} ({trade.side})")
                except Exception as exc:
                    log.warning(f"AutoTrader: end-of-session close failed for {trade.pair}: {exc}")
        return

    for trade in list(state.open_trades):
        try:
            await _check_breakeven(trade)
        except Exception as exc:
            log.debug(f"AutoTrader breakeven check {trade.pair}: {exc}")


async def _check_breakeven(trade) -> None:
    """If the trade has moved 1R in our favour, slide SL to break-even."""
    state = bot_state
    is_long = trade.side == "long"
    risk = abs(trade.entry - trade.stop)

    if risk <= 0:
        return

    # Fetch current mid price
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
    if profit < risk:
        return  # not yet at 1R

    # Set SL to entry + 1 pip buffer (so we never lose on a winner)
    buffer = pip_module.from_pips(trade.pair, 1.0)
    new_sl = (trade.entry + buffer) if is_long else (trade.entry - buffer)

    # Only move in the right direction (never tighten a SL already past BE)
    if is_long and trade.stop >= new_sl:
        return
    if not is_long and trade.stop <= new_sl:
        return

    try:
        await asyncio.to_thread(
            oanda.update_trade_stop_loss,
            state.token,
            state.account_id,
            trade.trade_id,
            new_sl,
            trade.pair,
            state.base_url,
        )
        with state._lock:
            trade.stop = new_sl
        log.info(f"AutoTrader {trade.pair}: moved SL to break-even @ {new_sl:.5f}")
    except Exception as exc:
        log.warning(f"AutoTrader {trade.pair}: BE move failed: {exc}")


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
        record = TradeRecord(
            pair=instr,
            side=side,
            units=abs(current_units),
            entry=entry,
            stop=float(sl_order.get("price", 0)),
            target=float(tp_order.get("price", 0)),
            opened_at=t.get("openTime", datetime.now(timezone.utc).isoformat()),
            trade_id=trade_id,
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

        with state._lock:
            trade.status = "closed"
            trade.closed_at = datetime.now(timezone.utc).isoformat()

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

    # ── Daily reset & loss-limit check ───────────────────────────────────────
    today = now.date()
    with state._lock:
        if state.session_date != today:
            state.session_date = today
            state.start_of_day_balance = nav
            state.daily_pl = 0.0
            state.trades_today = 0
            state.halted = False
            state.halt_reason = ""

    if state.start_of_day_balance and state.start_of_day_balance > 0:
        loss_pct = -state.daily_pl / state.start_of_day_balance
        if loss_pct >= cfg.daily_loss_limit_pct:
            msg = (
                f"Daily loss limit reached: −{loss_pct:.1%} "
                f"(limit −{cfg.daily_loss_limit_pct:.1%})"
            )
            with state._lock:
                state.halted = True
                state.halt_reason = msg
            log.warning(f"AutoTrader HALTED: {msg}")
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
            await _evaluate_pair(pair, nav, now)
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

    # ── Intraday signal ───────────────────────────────────────────────────────
    try:
        day_sig = compute_day_signal(pair, df_m5)
    except Exception as exc:
        log.debug(f"AutoTrader {pair}: signal error: {exc}")
        return

    if day_sig.action == "DAY_HOLD":
        return

    if day_sig.confidence < cfg.min_confidence:
        log.debug(
            f"AutoTrader {pair}: confidence {day_sig.confidence:.0%} < "
            f"threshold {cfg.min_confidence:.0%}"
        )
        return

    # ── Spread check ─────────────────────────────────────────────────────────
    try:
        pricing = await asyncio.to_thread(
            oanda.get_pricing,
            [pair],
            state.token,
            state.account_id,
            state.base_url,
        )
        instr = pip_module.normalize(pair)
        spread = (pricing.get(instr) or {}).get("spread_pips")
        if spread and spread > cfg.max_spread_pips:
            log.debug(f"AutoTrader {pair}: spread {spread:.1f} pips > max {cfg.max_spread_pips}")
            return
    except Exception:
        pass  # proceed without spread check on network error

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

    stop_price = day_sig.stop
    if stop_price is None:
        delta = pip_module.from_pips(pair, stop_pips)
        stop_price = (entry - delta) if is_buy else (entry + delta)

    target_pips = stop_pips * cfg.rr_ratio
    delta_tp = pip_module.from_pips(pair, target_pips)
    target_price = (entry + delta_tp) if is_buy else (entry - delta_tp)

    order_units = units if is_buy else -units

    log.info(
        f"AutoTrader: {day_sig.action} {pair} "
        f"{order_units:+,} units @ ~{entry:.5f}  "
        f"SL={stop_price:.5f}  TP={target_price:.5f}  "
        f"stop={stop_pips:.1f}pips  conf={day_sig.confidence:.0%}"
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
    )

    with state._lock:
        state.trades.append(record)
        state.trades_today += 1

    log.info(f"AutoTrader {pair}: order placed, trade_id={trade_id}")
