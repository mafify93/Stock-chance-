"""Position-sizing and risk math for the auto-trader.

All sizing is fixed-fractional: we risk a constant percentage of the
account's Net Asset Value (NAV) on every trade, then back into the unit
count from the stop distance in pips.

    units = (NAV × risk_pct) / (stop_pips × pip_value_per_unit)

pip_value_per_unit ≈ pip_size for USD-quoted pairs (EUR/USD, GBP/USD, etc.)
and is an approximation for other account currencies — OANDA applies the
precise conversion at fill time.
"""
from __future__ import annotations

from .. import pips as pip_module


def calculate_units(
    nav: float,
    risk_pct: float,
    stop_pips: float,
    pair: str,
    spot_price: float = 1.0,
    quote_to_usd: float | None = None,
) -> int:
    """Return integer unit count that risks `risk_pct` of `nav` on this trade.

    `nav` must be in USD. `quote_to_usd` is the USD value of one unit of the
    pair's quote currency; supplying it makes pip-value exact for every pair,
    including crosses (EUR/JPY etc.). Without it, cross pairs fall back to a
    legacy approximation that under-sizes them by the cross rate — so the live
    engine MUST pass quote_to_usd. `spot_price` is only used by that legacy path.

    Returns 0 if the inputs are degenerate (zero stop, zero nav, etc.).
    OANDA allows any integer unit count ≥ 1, so no rounding to lot sizes.
    """
    if stop_pips <= 0 or nav <= 0 or risk_pct <= 0:
        return 0
    risk_amount = nav * risk_pct
    pip_value = pip_module.pip_value_per_unit(pair, spot_price, quote_to_usd)
    if pip_value <= 0:
        return 0
    raw = risk_amount / (stop_pips * pip_value)
    return max(1, int(raw))


def expected_value(win_rate: float, rr_ratio: float, risk_pct: float) -> float:
    """Expected P&L per trade as a fraction of NAV.

    EV = (win_rate × rr_ratio × risk_pct) − ((1 − win_rate) × risk_pct)
    """
    return risk_pct * (win_rate * rr_ratio - (1 - win_rate))


def fractional_kelly(win_rate: float, rr_ratio: float, fraction: float = 0.25) -> float:
    """Quarter-Kelly stake as a fraction of NAV.

    Full Kelly: f* = (W·R − (1−W)) / R
    We use 1/4 Kelly by default — empirically reduces drawdown risk substantially
    while preserving most of the long-run growth rate.
    """
    if rr_ratio <= 0:
        return 0.0
    full_kelly = (win_rate * rr_ratio - (1 - win_rate)) / rr_ratio
    return max(0.0, full_kelly * fraction)
