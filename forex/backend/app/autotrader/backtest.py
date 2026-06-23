"""Historical backtester for the auto-trader strategy.

This replays past OANDA M5 candles through the *exact same* decision logic the
live engine uses (`compute_day_signal` + the entry/exit/sizing rules in
`engine.py`) and reports the realised expectancy **with spread costs included**.

The point of this module is honesty about cost. Every simulated trade pays the
full spread as a round-trip cost, so the net P&L reflects what OANDA would
actually have left you with — not a frictionless fantasy. Use it to answer the
only question that matters before risking real money: does this strategy have a
positive edge *after* costs, and how does trade frequency affect it?

Modelling choices (all deliberately conservative)
─────────────────────────────────────────────────
- No look-ahead: the signal is computed from *closed* bars up to bar i, and the
  entry fills at bar i+1's open.
- Spread: candles are mid prices. We detect stop/target hits on the mid path,
  then subtract the full `spread_pips` from each trade's gross result. That is
  the standard, slightly-pessimistic way to charge the spread.
- Both-touched ambiguity: if a single bar's range spans both the stop and the
  target, we assume the **stop** hit first (worst case).
- One position per pair at a time, mirroring the live `open_pairs` guard.
- Daily trade cap and the McKay consecutive-loss step-down are applied exactly
  as in the live engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from .. import pips as pip_module
from ..indicators import average_true_range
from ..intraday import compute_day_signal
from ..sessions import get_market_session
from ..signals import analyze as swing_analyze
from .config import AutoTraderConfig
from .engine import h1_blocks_trade
from .london_breakout import london_open_breakout
from .opening_range import opening_range_breakout
from .order_blocks import order_block_reversal
from .risk import calculate_units


@dataclass
class BacktestTrade:
    pair: str
    side: str            # "long" | "short"
    entry_time: str
    exit_time: str
    entry: float
    exit: float
    stop: float
    target: float
    units: int
    outcome: str         # "target" | "stop" | "eod" (end of data)
    gross_pips: float    # mid-to-mid move in our favour (can be negative)
    net_pips: float      # gross minus the full spread
    pnl_usd: float       # net_pips priced through units & pip value
    confidence: float
    signal_type: str = "ema_fallback"  # "london_breakout"|"orb"|"order_block"|"ema_fallback"


@dataclass
class BacktestStats:
    pair: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    gross_pips: float = 0.0
    spread_paid_pips: float = 0.0
    net_pips: float = 0.0
    avg_win_pips: float = 0.0
    avg_loss_pips: float = 0.0
    expectancy_pips: float = 0.0      # net pips per trade — the headline number
    profit_factor: float = 0.0        # gross win $ / gross loss $
    net_pnl_usd: float = 0.0
    return_pct: float = 0.0           # net P&L as % of starting NAV
    max_drawdown_pct: float = 0.0
    ending_nav: float = 0.0
    calmar_ratio: float = 0.0         # return_pct / max_drawdown_pct (higher = better risk-adj return)


def _mid_pips(pair: str, delta: float) -> float:
    return pip_module.to_pips(pair, delta)


def _resample_to_m15(df_m5: pd.DataFrame) -> pd.DataFrame:
    """Downsample M5 OHLCV bars to M15 for order-block analysis."""
    return (
        df_m5.resample("15min", label="left", closed="left")
        .agg(Open=("Open", "first"), High=("High", "max"),
             Low=("Low", "min"), Close=("Close", "last"),
             Volume=("Volume", "sum"))
        .dropna(subset=["Open"])
    )


def _try_ict_signals(
    pair: str,
    window_m5: pd.DataFrame,
    bar_dt: datetime,
    cfg: AutoTraderConfig,
    m15_full: "pd.DataFrame | None" = None,
) -> "tuple | None":
    """Attempt ICT strategies in priority order; return (signal, strategy_name) or None.

    Silver Bullet and ICT Sweep are live-only (require M1 bars not available
    in the M5 backtest dataset).

    m15_full is the pre-resampled M15 frame for the whole pair history. When
    supplied, we slice it rather than resampling on every bar (avoids O(n²) cost).
    """
    hour = bar_dt.hour

    # 1. London Open Breakout (07:00–10:00 UTC, M5 compatible)
    if cfg.use_london_breakout and pair in cfg.london_breakout_pairs and 7 <= hour < 10:
        try:
            sig = london_open_breakout(pair, window_m5, bar_dt)
            if sig and sig.action != "DAY_HOLD" and sig.stop_pips:
                return sig, "london_breakout"
        except Exception:
            pass

    # 2. Opening Range Breakout (13:15–17:00 UTC, M5 compatible)
    if cfg.use_orb and 13 <= hour < 17:
        try:
            sig = opening_range_breakout(pair, window_m5, bar_dt)
            if sig and sig.action != "DAY_HOLD" and sig.stop_pips:
                return sig, "orb"
        except Exception:
            pass

    # 3. Order Block Reversal (07:00–20:00 UTC, M15 pre-resampled)
    if cfg.use_order_blocks and 7 <= hour < 20:
        try:
            if m15_full is not None:
                m15 = m15_full[m15_full.index <= bar_dt]
            else:
                m15 = _resample_to_m15(window_m5)
            if len(m15) >= 5:
                sig = order_block_reversal(pair, m15, bar_dt)
                if sig and sig.action != "DAY_HOLD" and sig.stop_pips:
                    return sig, "order_block"
        except Exception:
            pass

    return None


def simulate_pair(
    pair: str,
    df: pd.DataFrame,
    cfg: AutoTraderConfig,
    spread_pips: float,
    starting_nav: float,
    h1_df: pd.DataFrame | None = None,
) -> tuple[list[BacktestTrade], float]:
    """Walk one pair's M5 history bar-by-bar and return (trades, ending_nav).

    `df` must be a chronologically-sorted M5 OHLCV frame indexed by UTC time,
    exactly as `oanda.get_candles` returns it.
    `h1_df` is the same pair's H1 history. When `cfg.h1_trend_filter` is on and
    H1 data is supplied, entries that fight the H1 trend are skipped — exactly
    as the live engine does.
    """
    trades: list[BacktestTrade] = []
    nav = starting_nav
    risk_scale = 1.0
    consecutive_losses = 0

    trades_today = 0
    current_day = None

    # Pre-compute NY session open price (first bar open at/after 13:00 UTC) per day.
    # Used by the NY momentum filter to gate EMA entries: a buy signal is only valid
    # if the NY session is actually trending up (current price > NY open), and vice
    # versa. This replaces ORB's accidental "gate" mechanic with an explicit, meaningful
    # filter that doesn't require running a net-negative strategy to achieve it.
    ny_open_by_day: dict = {}
    for ts_idx, row_data in df.iterrows():
        h = ts_idx.hour if hasattr(ts_idx, "hour") else ts_idx.to_pydatetime().hour
        d = ts_idx.date()
        if h == 13 and d not in ny_open_by_day:
            ny_open_by_day[d] = float(row_data["Open"])

    # Pre-resample M15 once for the whole pair so _try_ict_signals can slice
    # it by timestamp instead of resampling on every bar (avoids O(n²) cost).
    m15_precomputed: pd.DataFrame | None = None
    if cfg.use_order_blocks:
        try:
            m15_precomputed = _resample_to_m15(df)
        except Exception:
            pass

    # Pre-compute ATR14 for the ATR expansion regime filter.
    # Breakout strategies (London Breakout, ORB) need expanding volatility to work —
    # when ATR is contracting the market is in a range and breakouts get faded.
    atr_series: pd.Series | None = None
    if cfg.use_atr_expansion_filter:
        try:
            atr_series = average_true_range(df, 14)
        except Exception:
            pass

    # Pre-compute one H1 swing score per H1 bar (no look-ahead): each is the
    # score from the closed H1 bars up to and including that timestamp.
    h1_timeline: list[tuple[pd.Timestamp, float]] = []
    if cfg.h1_trend_filter and h1_df is not None and len(h1_df) >= 50:
        for hi in range(49, len(h1_df)):
            try:
                h1_timeline.append(
                    (h1_df.index[hi], swing_analyze(pair, h1_df.iloc[: hi + 1]).score)
                )
            except Exception:
                pass

    def _h1_score_at(ts: pd.Timestamp) -> float | None:
        score = None
        for h1_ts, h1_s in h1_timeline:
            if h1_ts <= ts:
                score = h1_s
            else:
                break
        return score

    i = 25  # warm-up so EMA20 / opening-range have data
    n = len(df)
    while i < n - 1:
        bar_time = df.index[i]
        day = bar_time.date()
        if day != current_day:
            current_day = day
            trades_today = 0

        if trades_today >= cfg.max_trades_per_day:
            i += 1
            continue

        # ── Session gate (mirror the live engine) ─────────────────────────────
        if cfg.session_filter:
            session = get_market_session(bar_time.to_pydatetime())
            if session.status != "open" or not (
                set(session.active_sessions) & {"London", "New York"}
            ):
                i += 1
                continue

        # ── Signal on closed bars [.. i] ──────────────────────────────────────
        window = df.iloc[: i + 1]
        bar_dt = bar_time.to_pydatetime()

        # Try ICT strategies first (London breakout, ORB, Order Block)
        ict_result = _try_ict_signals(pair, window, bar_dt, cfg, m15_full=m15_precomputed)
        signal_type = "ema_fallback"

        if ict_result is not None:
            sig, strategy_name = ict_result
            # ATR expansion filter: breakout strategies need expanding volatility.
            # When ATR is below ~80% of its recent average the market is consolidating
            # and breakouts tend to get faded — skip London Breakout and ORB entries.
            if (cfg.use_atr_expansion_filter
                    and strategy_name in ("london_breakout", "orb")
                    and atr_series is not None):
                atr_val = atr_series.iloc[i]
                lb_start = max(0, i - cfg.atr_expansion_lookback)
                atr_mean = atr_series.iloc[lb_start:i].mean()
                if not pd.isna(atr_val) and not pd.isna(atr_mean) and atr_mean > 0:
                    if atr_val < atr_mean * 0.8:
                        ict_result = None  # consolidating — skip this breakout signal
            if ict_result is not None:
                signal_type = strategy_name

        # Fallback: intraday VWAP/RSI/EMA signal
        if ict_result is None:
            # Hard time gate (off by default — too broad, removes good trades).
            if cfg.block_ema_ny_open and 13 <= bar_dt.hour < 17:
                i += 1
                continue
            try:
                sig = compute_day_signal(pair, window)
            except Exception:
                i += 1
                continue

            # ATR expansion filter extended to EMA during NY open (13:00–16:00 UTC).
            # When ATR is contracting at NY open the market is ranging; EMA crossovers
            # in a range are noise. The same ATR guard already protects breakout
            # strategies — now it protects EMA during the same choppy window.
            if (cfg.use_atr_expansion_filter
                    and atr_series is not None
                    and 13 <= bar_dt.hour < 16):
                atr_val = atr_series.iloc[i]
                lb_start = max(0, i - cfg.atr_expansion_lookback)
                atr_mean = atr_series.iloc[lb_start:i].mean()
                if (not pd.isna(atr_val) and not pd.isna(atr_mean)
                        and atr_mean > 0 and atr_val < atr_mean * 0.8):
                    i += 1
                    continue  # ranging NY open — skip EMA

            # NY open momentum alignment (13:00–16:00 UTC).
            # EMA uses a London-anchored VWAP that carries the London session's
            # directional bias into NY open. This can generate buy signals right as
            # NY participants take profit and reverse. The filter gates EMA entries
            # to only fire when price confirms the NY session's actual direction.
            if cfg.use_ny_open_momentum_filter and 13 <= bar_dt.hour < 16:
                ny_ref = ny_open_by_day.get(bar_dt.date())
                if ny_ref is not None:
                    cur = float(df["Close"].iloc[i])
                    if sig.action == "DAY_BUY" and cur <= ny_ref:
                        i += 1
                        continue  # NY session bearish — skip EMA buy
                    if sig.action == "DAY_SELL" and cur >= ny_ref:
                        i += 1
                        continue  # NY session bullish — skip EMA sell
        else:
            sig, _ = ict_result

        if sig.action == "DAY_HOLD" or sig.confidence < cfg.min_confidence * 100:
            i += 1
            continue

        # ── H1 trend filter (mirror the live engine) ──────────────────────────
        if cfg.h1_trend_filter and h1_blocks_trade(sig.action, _h1_score_at(bar_time)):
            i += 1
            continue

        raw_stop = sig.stop_pips
        if raw_stop is None or raw_stop <= 0:
            i += 1
            continue
        stop_pips = max(cfg.min_stop_pips, min(cfg.max_stop_pips, raw_stop))
        target_pips = stop_pips * cfg.rr_ratio

        is_long = sig.action == "DAY_BUY"

        # ── Fill at next bar's open ───────────────────────────────────────────
        entry_idx = i + 1
        entry = float(df["Open"].iloc[entry_idx])
        entry_time = df.index[entry_idx]

        stop_delta = pip_module.from_pips(pair, stop_pips)
        tgt_delta = pip_module.from_pips(pair, target_pips)
        if is_long:
            stop_price = entry - stop_delta
            target_price = entry + tgt_delta
        else:
            stop_price = entry + stop_delta
            target_price = entry - tgt_delta

        units = calculate_units(nav, cfg.risk_pct * risk_scale, stop_pips, pair, entry)
        if units < 1:
            i += 1
            continue

        # ── Walk forward until stop or target is touched ──────────────────────
        # Breakeven fires when price reaches cfg.breakeven_r × stop distance
        # (same formula as the live engine), then moves the stop to entry + (spread+1) pips.
        # The spread+1 buffer ensures breakeven exits always produce a small positive
        # net result even after the round-trip spread is deducted — otherwise a 1-pip
        # gross exit at 1 pip spread charges zero net and distorts win rate calculations.
        be_buffer = pip_module.from_pips(pair, spread_pips + 1.0)
        be_advance = stop_delta * cfg.breakeven_r   # e.g. 0.5 × 15 pips = 7.5 pips
        if is_long:
            be_trigger = entry + be_advance
            be_stop = entry + be_buffer
        else:
            be_trigger = entry - be_advance
            be_stop = entry - be_buffer

        outcome = "eod"
        exit_price = float(df["Close"].iloc[-1])
        exit_time = df.index[-1]
        cur_stop = stop_price
        armed = False
        j = entry_idx
        while j < n:
            hi = float(df["High"].iloc[j])
            lo = float(df["Low"].iloc[j])
            if is_long:
                stop_hit = lo <= cur_stop
                tgt_hit = hi >= target_price
            else:
                stop_hit = hi >= cur_stop
                tgt_hit = lo <= target_price
            if stop_hit:  # worst-case priority
                outcome = "breakeven" if armed else "stop"
                exit_price = cur_stop
                exit_time = df.index[j]
                break
            if cfg.breakeven_stop and not armed:
                if (is_long and hi >= be_trigger) or (not is_long and lo <= be_trigger):
                    armed = True
                    cur_stop = be_stop
            if tgt_hit:
                outcome = "target"
                exit_price = target_price
                exit_time = df.index[j]
                break
            j += 1

        gross = (exit_price - entry) if is_long else (entry - exit_price)
        gross_pips = round(_mid_pips(pair, gross), 1)
        net_pips = round(gross_pips - spread_pips, 1)

        pip_value = pip_module.pip_value_per_unit(pair, entry)
        pnl_usd = net_pips * pip_value * units
        nav += pnl_usd

        trades.append(
            BacktestTrade(
                pair=pair,
                side="long" if is_long else "short",
                entry_time=entry_time.isoformat(),
                exit_time=exit_time.isoformat(),
                entry=round(entry, 6),
                exit=round(exit_price, 6),
                stop=round(stop_price, 6),
                target=round(target_price, 6),
                units=units,
                outcome=outcome,
                gross_pips=gross_pips,
                net_pips=net_pips,
                pnl_usd=round(pnl_usd, 2),
                confidence=sig.confidence,
                signal_type=signal_type,
            )
        )
        trades_today += 1

        # McKay step-down on the net result
        if net_pips <= 0:
            consecutive_losses += 1
        else:
            consecutive_losses = 0
        if consecutive_losses == 0:
            risk_scale = 1.0
        elif consecutive_losses == 1:
            risk_scale = 0.75
        else:
            risk_scale = 0.50

        # Resume scanning from the bar after the exit (one position per pair).
        i = max(entry_idx + 1, j + 1)

    return trades, nav


def summarize(pair: str, trades: list[BacktestTrade], starting_nav: float, ending_nav: float) -> BacktestStats:
    """Aggregate a list of trades into headline statistics."""
    stats = BacktestStats(pair=pair, ending_nav=round(ending_nav, 2))
    if not trades:
        return stats

    wins = [t for t in trades if t.net_pips > 0]
    losses = [t for t in trades if t.net_pips <= 0]

    stats.trades = len(trades)
    stats.wins = len(wins)
    stats.losses = len(losses)
    stats.win_rate = round(len(wins) / len(trades) * 100, 1)
    stats.gross_pips = round(sum(t.gross_pips for t in trades), 1)
    stats.spread_paid_pips = round(sum(t.gross_pips - t.net_pips for t in trades), 1)
    stats.net_pips = round(sum(t.net_pips for t in trades), 1)
    stats.avg_win_pips = round(sum(t.net_pips for t in wins) / len(wins), 1) if wins else 0.0
    stats.avg_loss_pips = round(sum(t.net_pips for t in losses) / len(losses), 1) if losses else 0.0
    stats.expectancy_pips = round(stats.net_pips / len(trades), 2)

    gross_win_usd = sum(t.pnl_usd for t in wins)
    gross_loss_usd = abs(sum(t.pnl_usd for t in losses))
    stats.profit_factor = round(gross_win_usd / gross_loss_usd, 2) if gross_loss_usd > 0 else 0.0

    stats.net_pnl_usd = round(sum(t.pnl_usd for t in trades), 2)
    stats.return_pct = round(stats.net_pnl_usd / starting_nav * 100, 2) if starting_nav > 0 else 0.0

    # Max drawdown on the equity curve.
    equity = starting_nav
    peak = starting_nav
    max_dd = 0.0
    for t in trades:
        equity += t.pnl_usd
        peak = max(peak, equity)
        if peak > 0:
            dd = (peak - equity) / peak
            max_dd = max(max_dd, dd)
    stats.max_drawdown_pct = round(max_dd * 100, 2)
    stats.calmar_ratio = round(stats.return_pct / stats.max_drawdown_pct, 2) if stats.max_drawdown_pct > 0 else 0.0
    return stats


def run_backtest(
    candles_by_pair: dict[str, pd.DataFrame],
    cfg: AutoTraderConfig,
    spread_pips_by_pair: dict[str, float],
    starting_nav: float,
    h1_candles_by_pair: dict[str, pd.DataFrame] | None = None,
) -> dict:
    """Run the full backtest across every pair and return a JSON-able summary.

    `candles_by_pair` maps a pair to its M5 OHLCV DataFrame.
    `spread_pips_by_pair` maps a pair to the spread (in pips) to charge per trade.
    `h1_candles_by_pair` maps a pair to its H1 DataFrame for the H1 trend filter.
    """
    per_pair: list[BacktestStats] = []
    all_trades: list[BacktestTrade] = []
    nav = starting_nav

    for pair, df in candles_by_pair.items():
        spread = spread_pips_by_pair.get(pair, 1.0)
        h1_df = (h1_candles_by_pair or {}).get(pair)
        pair_start = nav
        trades, nav = simulate_pair(pair, df, cfg, spread, pair_start, h1_df=h1_df)
        per_pair.append(summarize(pair, trades, pair_start, nav))
        all_trades.extend(trades)

    all_trades.sort(key=lambda t: t.entry_time)
    overall = summarize("ALL", all_trades, starting_nav, nav)

    # Per-strategy breakdown: group all trades by signal_type and summarise each.
    # This reveals which strategy is driving profits and which is causing drawdowns.
    from collections import defaultdict
    by_strategy: dict[str, list[BacktestTrade]] = defaultdict(list)
    for t in all_trades:
        by_strategy[t.signal_type].append(t)

    per_strategy: list[BacktestStats] = []
    for strategy_name in ("london_breakout", "orb", "order_block", "ema_fallback"):
        strategy_trades = by_strategy.get(strategy_name, [])
        if not strategy_trades:
            continue
        st_pnl = sum(t.pnl_usd for t in strategy_trades)
        st_stats = summarize(strategy_name, strategy_trades, starting_nav, starting_nav + st_pnl)
        per_strategy.append(st_stats)

    return {
        "starting_nav": round(starting_nav, 2),
        "ending_nav": round(nav, 2),
        "config": {
            "risk_pct": cfg.risk_pct,
            "rr_ratio": cfg.rr_ratio,
            "min_confidence": cfg.min_confidence,
            "session_filter": cfg.session_filter,
            "h1_trend_filter": cfg.h1_trend_filter,
            "breakeven_stop": cfg.breakeven_stop,
            "max_trades_per_day": cfg.max_trades_per_day,
            "min_stop_pips": cfg.min_stop_pips,
            "max_stop_pips": cfg.max_stop_pips,
            "use_atr_expansion_filter": cfg.use_atr_expansion_filter,
        },
        "overall": overall.__dict__,
        "per_pair": [s.__dict__ for s in per_pair],
        "per_strategy": [s.__dict__ for s in per_strategy],
        "trade_count": len(all_trades),
        "trades": [t.__dict__ for t in all_trades[:200]],  # cap payload
    }
