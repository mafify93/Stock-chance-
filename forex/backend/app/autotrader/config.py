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
    min_stop_pips: float = 8.0      # clamp stop distance from below
    max_stop_pips: float = 30.0     # clamp stop distance from above
    breakeven_stop: bool = True     # at 1R profit, slide stop to entry + 1 pip

    # --- Position management ---
    max_positions: int = 2          # max concurrent open bot positions
    max_trades_per_day: int = 50    # daily trade cap
    daily_loss_limit_pct: float = 0.03  # halt if daily P&L < −3 % of start balance

    # --- Entry filters ---
    min_confidence: float = 0.50    # minimum intraday signal confidence (0–1 scale)
    max_spread_pips: float = 3.0    # skip pair if live spread exceeds this
    session_filter: bool = True     # only trade during London or NY sessions
    h1_trend_filter: bool = False   # OFF: backtest proved harmful
    signal_confirmation: bool = True  # require same signal on 2 consecutive scans
                                      # before entering — eliminates one-bar whipsaws

    # --- Trade management ---
    partial_tp: bool = True         # close 50% at 1R profit; let rest run with BE stop
    time_decay_stop: bool = True    # instead of hard-closing a stale losing trade,
                                    # progressively tighten its stop as it ages
    max_trade_hours: float = 3.0    # by this age, a losing trade's stop has fully
                                    # decayed in to its minimum room (no market close)

    # --- Scan schedule ---
    scan_interval_minutes: int = 5  # how often the engine scans the pair list

    # --- Universe ---
    pairs: list[str] = field(default_factory=lambda: [
        "EUR_USD", "GBP_USD", "USD_JPY", "EUR_JPY", "GBP_JPY",
    ])
