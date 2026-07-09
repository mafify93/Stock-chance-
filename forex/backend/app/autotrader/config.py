"""Configurable parameters for the auto-trader bot.

All values have conservative defaults sized for a ~$200 practice account.
The iOS app exposes these in the Auto-Trade settings screen so the user can
tune them without touching code.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AutoTraderConfig:
    # --- Risk / sizing ---
    risk_pct: float = 0.01          # fraction of NAV to risk per trade (1 %)
    max_leverage: float = 20.0      # cap position notional at this × NAV so orders
                                    # don't get cancelled for INSUFFICIENT_MARGIN
                                    # (OANDA retail majors ~30:1; 20 leaves a buffer)
    rr_ratio: float = 2.0           # reward-to-risk ratio for take-profit placement
    min_stop_pips: float = 12.0     # clamp stop distance from below
    max_stop_pips: float = 30.0     # clamp stop distance from above
    breakeven_stop: bool = True     # slide stop to entry + 1 pip once profit ≥ breakeven_r × risk
    breakeven_r: float = 1.0        # fraction of 1R at which breakeven fires (1.0 = full stop away = out of noise zone)
    profit_lock_pips: float = 999.0 # pip-based breakeven trigger; 999 = disabled (rely on R-based only)
    hwm_close: bool = False         # disabled: was closing every winning trade at 0.00 before target
    hwm_r: float = 0.5              # require 0.5R of profit before HWM fires (avoids scratching noise)

    # --- Position management ---
    max_positions: int = 2          # max concurrent open bot positions
    max_trades_per_day: int = 50    # daily trade cap
    daily_loss_halt_pct: float = 0.03  # pause trading today if daily P&L drops below
                                       # this fraction of start-of-day balance (3%);
                                       # resets automatically next session. 0 = disabled.

    # --- Prop-firm challenge mode ---
    # Funded-account evaluations (FTMO, Topstep, etc.) fail you the instant
    # equity breaches a daily-loss or max-total-loss limit. These guardrails halt
    # the bot BEFORE those limits with a safety buffer, so a challenge can't be
    # blown. The buffers are deliberately tighter than the typical firm limits
    # (5% daily / 10% total) because an open position's floating loss can move
    # equity between scans. When prop_mode is on, the engine measures drawdown
    # from a fixed account_start_balance that never resets daily.
    prop_mode: bool = False
    prop_daily_loss_pct: float = 0.04    # halt for the day at -4% (firms fail at ~5%)
    prop_max_total_loss_pct: float = 0.08  # halt permanently at -8% from start (fail at ~10%)
    prop_profit_target_pct: float = 0.10   # stop & lock in once +10% target is reached

    # --- Entry filters ---
    min_confidence: float = 0.70    # minimum intraday signal confidence (0–1 scale)
    max_spread_pips: float = 2.0    # skip pair if live spread exceeds this
    session_filter: bool = True     # only trade during London or NY sessions
    h1_trend_filter: bool = False   # OFF: backtest proved harmful
    signal_confirmation: bool = True  # require same signal on 2 consecutive scans
                                      # before entering — eliminates one-bar whipsaws
    block_rollover: bool = True     # no entries during the ~17:00 ET rollover spread spike
    news_blackout_utc: list[str] = field(default_factory=list)
                                    # "HH:MM-HH:MM" UTC windows to skip (high-impact news);
                                    # empty = disabled (no economic-calendar feed wired in)

    # --- Trade management ---
    partial_tp: bool = True         # close 50% at 1R profit; let rest run
    time_decay_stop: bool = True    # instead of hard-closing a stale losing trade,
                                    # progressively tighten its stop as it ages
    max_trade_hours: float = 3.0    # by this age, a losing trade's stop has fully
                                    # decayed in to its minimum room (no market close)
    # Runner management: after the partial, trail the remaining units with an
    # ATR (Chandelier-style) stop floored at break-even, rather than parking the
    # stop at entry and waiting for a fixed target. Lets winners run past 2R
    # while the original 2R take-profit stays on as a hybrid trail+limit exit.
    trail_runner: bool = True
    trail_atr_period: int = 14      # ATR lookback (M5 bars) for the trailing stop
    trail_atr_mult: float = 2.0     # stop sits this many ATRs below the high-since-entry

    # --- Scan schedule ---
    scan_interval_minutes: int = 5  # how often the engine scans the pair list

    # --- London Open Breakout ---
    use_london_breakout: bool = False       # backtested PF 0.50, Calmar -1.00 — net-negative; disabled
    london_breakout_pairs: list[str] = field(default_factory=lambda: [
        "GBP_JPY",                          # cleanest London breakout; EUR_JPY adds noise
    ])

    # --- AI self-learning ---
    use_ai_learner: bool = True             # adjust confidence using trade outcome history
    ai_min_win_prob: float = 0.35           # skip entry if learner estimates win prob < 35%

    # --- ICT Session Sweep ---
    use_ict_sweep: bool = True              # NY 9am setup: Asia/London range sweep + FVG reversal

    # --- Opening Range Breakout ---
    use_orb: bool = False                   # backtested PF 0.97, Calmar -0.07 — net-negative; disabled

    # --- EMA/intraday time gate ---
    block_ema_ny_open: bool = False         # skip EMA fallback during 13:00–17:00 UTC (NY open)
                                            # tested False — gate removes good trades alongside bad ones

    # --- EMA fallback kill-switch ---
    # When False, the EMA/VWAP/RSI intraday signal is completely disabled and
    # only ICT strategies (London Breakout, ICT Sweep, Silver Bullet) run.
    # Use this in the backtest to isolate London Breakout's standalone edge —
    # if Calmar improves without EMA, the EMA is the leak.
    use_ema_fallback: bool = True

    # --- EMA session time window ---
    # The session_filter gates on "London or NY open" — a 10-hour window that
    # includes ~5 hours of London lunch and drift (09:30–13:30 UTC) where EMA
    # crossovers are pure ranging-market noise. Restricting EMA to the two
    # genuine momentum windows cuts eligible bars by ~60% while keeping the
    # trades that actually follow through.
    ema_session_window: bool = False  # backtest proved harmful — cuts 75% of trades and drops
                                      # WR from 61% → 40%; session_filter alone is sufficient

    # --- Mean reversion (range-regime complement to the momentum strategy) ---
    # Momentum bleeds in ranges; this fades Bollinger-band extremes back to
    # the mean ONLY while ADX says the market is ranging. Off by default —
    # must earn its place via /backtest-live A/B before going live.
    use_mean_reversion: bool = False
    mr_adx_max: float = 20.0     # only fade when ADX(14) is BELOW this (ranging)
    mr_rr_ratio: float = 1.0     # reversion targets the mean, not a runner:
                                 # ~1:1 with a high win rate, vs momentum's 2:1

    # --- ADX ranging-market gate ---
    # EMA entries are suppressed when ADX(14) falls below this threshold —
    # below it the market is ranging and EMA crossovers are noise, not signal.
    # Default 15 is the original, validated value. Raising it (e.g. 20-22)
    # excludes the ADX 14-19 "borderline trend" zone where false breakouts
    # cluster — tested via /backtest-live A/B before changing the live default.
    adx_threshold: float = 15.0

    # --- Per-pair active trading hours (UTC) ---
    # When set (via a pair's override profile), restricts that pair to its genuine
    # high-liquidity directional hours instead of the generic London+NY window.
    # This is the single biggest per-pair edge driver: each currency trends during
    # its own financial centre's session. Trading USD/JPY during dead London hours
    # (when it just chops) is what produced its 7% win rate. Format: list of
    # [start_hour, end_hour) UTC windows, e.g. [[13, 16]]. None = no restriction
    # beyond the standard session_filter.
    active_hours_utc: list | None = None

    # --- NY open momentum alignment ---
    use_ny_open_momentum_filter: bool = True  # during 13:00–16:00 UTC, only take EMA entries
                                              # that align with the actual NY session direction
                                              # (price vs. first 13:00 UTC bar open). Prevents
                                              # EMA from fading NY open moves based on stale
                                              # London VWAP direction.

    # --- ICT Silver Bullet ---
    use_silver_bullet: bool = True          # FVG entries at 07:00, 14:00, 18:00 UTC windows

    # --- Order Block Reversal ---
    use_order_blocks: bool = False          # backtested PF 0.94 — net-negative; disabled by default

    # --- Volatility regime filter ---
    use_atr_expansion_filter: bool = True   # skip London Breakout / ORB when ATR < recent avg
                                            # (contracting ATR = ranging market = bad for breakouts)
    atr_expansion_lookback: int = 20        # number of M5 bars to average ATR over for the check

    # --- Universe ---
    # EUR/JPY: 41% WR, Calmar 4.08 — proven primary pair.
    # Additional pairs are tuned via per-pair profiles below and must each pass
    # a standalone backtest (positive PF + Calmar) before being added here.
    pairs: list[str] = field(default_factory=lambda: [
        "EUR_JPY",
    ])

    # --- Per-pair tuning profiles ---
    # The global defaults above are tuned for EUR/JPY. Other pairs have different
    # volatility, spread, and trend personality, so running one-size-fits-all
    # settings on them fails (GBP/JPY scored 28% WR that way). Each entry here
    # overrides only the listed fields for that pair; anything omitted falls back
    # to the global default. Resolve with `cfg.resolved_for(pair)`.
    #
    # These are *researched starting points*, not validated numbers — backtest
    # each pair ALONE in the app and only add a pair to `pairs` once it shows a
    # positive profit factor and Calmar on its own.
    # Confidence is kept at the EUR/JPY-proven 0.68–0.70 so each pair generates
    # a statistically meaningful sample (a 0.75+ bar choked them to 3–4 trades
    # over 2 weeks — too few to judge). The real per-pair differentiation is in
    # stop sizing and spread tolerance, matched to each pair's volatility.
    pair_overrides: dict = field(default_factory=lambda: {
        # GBP/JPY: most volatile major-cross. Big trends but whippy/news-spiky
        # with naturally wider spreads — give stops more room, tolerate spread.
        # Active hours: London open is when GBP and JPY desks overlap and the
        # pair makes its cleanest directional moves; it chops the rest of the day.
        "GBP_JPY": {
            "min_confidence": 0.70,
            "rr_ratio": 2.0,
            "min_stop_pips": 15.0,
            "max_stop_pips": 40.0,
            "max_spread_pips": 3.5,
            "active_hours_utc": [[7, 11]],          # London open
        },
        # EUR/USD: lowest volatility, tightest spread, ranges more than it trends.
        # Tighter stops to match its smaller daily range, tight spread gate.
        # Active hours: the London–NY overlap (12:00–16:00 UTC) is the only window
        # EUR/USD reliably trends; outside it the pair ranges and momentum logic
        # whipsaws (the 22% WR came from trading it all day).
        "EUR_USD": {
            "min_confidence": 0.68,
            "rr_ratio": 2.0,
            "min_stop_pips": 8.0,
            "max_stop_pips": 22.0,
            "max_spread_pips": 1.5,
            "active_hours_utc": [[12, 16]],         # London–NY overlap
        },
        # GBP/USD ("cable"): moderate volatility, trends well at London/NY open.
        # Two genuine momentum windows: London open and the NY-overlap morning.
        "GBP_USD": {
            "min_confidence": 0.68,
            "rr_ratio": 2.0,
            "min_stop_pips": 10.0,
            "max_stop_pips": 28.0,
            "max_spread_pips": 2.0,
            "active_hours_utc": [[7, 10], [13, 16]],  # London open + NY overlap
        },
        # USD/JPY: trends smoothly, tight spread, moderate range. JPY trades on
        # the Tokyo session and USD on the NY session, so its directional moves
        # cluster at the Tokyo open and the NY morning — NOT during London, where
        # one-size-fits-all timing trapped it into a 7% win rate.
        "USD_JPY": {
            "min_confidence": 0.68,
            "rr_ratio": 2.0,
            "min_stop_pips": 10.0,
            "max_stop_pips": 28.0,
            "max_spread_pips": 1.8,
            "active_hours_utc": [[0, 3], [13, 16]],   # Tokyo open + NY morning
        },
    })

    def resolved_for(self, pair: str) -> "AutoTraderConfig":
        """Return a copy of this config with the pair's overrides applied.

        Fields not listed in the pair's override entry keep the global value.
        Pairs with no entry get an unmodified copy. Used by both the live engine
        and the backtester so each pair trades with settings suited to its
        volatility/spread personality instead of one-size-fits-all values.
        """
        import dataclasses

        overrides = (self.pair_overrides or {}).get(pair)
        if not overrides:
            return self
        valid = {f.name for f in dataclasses.fields(self)}
        clean = {k: v for k, v in overrides.items() if k in valid}
        return dataclasses.replace(self, **clean)

    def in_active_hours(self, hour_utc: int) -> bool:
        """True if `hour_utc` falls in one of this config's active_hours_utc
        windows. Returns True when no windows are configured (no restriction).

        Each window is [start, end) in UTC hours. Windows may wrap midnight
        (start > end), e.g. [22, 2] covers 22:00–01:59.
        """
        windows = self.active_hours_utc
        if not windows:
            return True
        for start, end in windows:
            if start <= end:
                if start <= hour_utc < end:
                    return True
            else:  # wraps midnight
                if hour_utc >= start or hour_utc < end:
                    return True
        return False
