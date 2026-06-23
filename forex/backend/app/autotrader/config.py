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
    rr_ratio: float = 2.0           # reward-to-risk ratio for take-profit placement
    min_stop_pips: float = 12.0     # clamp stop distance from below
    max_stop_pips: float = 30.0     # clamp stop distance from above
    breakeven_stop: bool = True     # slide stop to entry + 1 pip once profit ≥ breakeven_r × risk
    breakeven_r: float = 0.5        # fraction of 1R at which breakeven fires (0.5 = half the stop)
    profit_lock_pips: float = 8.0   # also fire breakeven when profit hits this many pips (whichever
                                    # triggers first: R-based or pip-based)
    hwm_close: bool = True          # close immediately if trade was up ≥ hwm_r and falls back to 0
    hwm_r: float = 0.5              # require 0.5R of profit before HWM fires (avoids scratching noise)

    # --- Position management ---
    max_positions: int = 2          # max concurrent open bot positions
    max_trades_per_day: int = 50    # daily trade cap

    # --- Entry filters ---
    min_confidence: float = 0.65    # minimum intraday signal confidence (0–1 scale)
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
    use_london_breakout: bool = True        # use Asian-range breakout at London open
    london_breakout_pairs: list[str] = field(default_factory=lambda: [
        "EUR_USD", "GBP_USD",               # tightest spreads, cleanest breakouts
    ])

    # --- AI self-learning ---
    use_ai_learner: bool = True             # adjust confidence using trade outcome history
    ai_min_win_prob: float = 0.35           # skip entry if learner estimates win prob < 35%

    # --- ICT Session Sweep ---
    use_ict_sweep: bool = True              # NY 9am setup: Asia/London range sweep + FVG reversal

    # --- Opening Range Breakout ---
    use_orb: bool = True                    # NY open 15-min range breakout (13:15–17:00 UTC)

    # --- ICT Silver Bullet ---
    use_silver_bullet: bool = True          # FVG entries at 07:00, 14:00, 18:00 UTC windows

    # --- Order Block Reversal ---
    use_order_blocks: bool = True           # last opposing candle before impulse (M15)

    # --- Universe ---
    pairs: list[str] = field(default_factory=lambda: [
        "EUR_USD", "GBP_USD", "USD_JPY", "EUR_JPY", "GBP_JPY",
    ])
