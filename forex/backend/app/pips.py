"""Pip math for currency pairs.

A *pip* is the standard unit of price movement in forex. For most pairs one
pip is the 4th decimal place (0.0001); for JPY-quoted pairs it's the 2nd
decimal place (0.01). Almost every forex concept the app shows the user -
spread, stop distance, "suspected profit" - is expressed in pips, so this
module is the single source of truth for converting between price and pips.
"""
from __future__ import annotations

# Pairs quoted in JPY (and a few exotics) use 0.01 as one pip instead of
# the usual 0.0001. Gold (XAU) shares this convention too, as the BASE
# currency rather than the quote — confirmed via OANDA's own instrument
# metadata (pipLocation -2, displayPrecision 3), not assumed; a wrong
# assumption here caused the worst sizing bug in this project's history.
JPY_QUOTED = ("JPY",)
_TWO_DECIMAL_PIP_BASE = ("XAU",)


def pip_size(pair: str) -> float:
    """Price increment of a single pip for `pair` (e.g. "EUR_USD" -> 0.0001)."""
    if quote_currency(pair) in JPY_QUOTED or base_currency(pair) in _TWO_DECIMAL_PIP_BASE:
        return 0.01
    return 0.0001


def price_decimals(pair: str) -> int:
    """How many decimals to display a price with (one more than the pip,
    matching OANDA's fractional-pip pricing)."""
    if quote_currency(pair) in JPY_QUOTED or base_currency(pair) in _TWO_DECIMAL_PIP_BASE:
        return 3
    return 5


def base_currency(pair: str) -> str:
    return normalize(pair).split("_")[0]


def quote_currency(pair: str) -> str:
    return normalize(pair).split("_")[1]


def normalize(pair: str) -> str:
    """Accept "EUR/USD", "eurusd", "EUR-USD" etc. and return OANDA's
    canonical "EUR_USD" form."""
    cleaned = pair.upper().replace("/", "_").replace("-", "_").strip()
    if "_" in cleaned:
        return cleaned
    if len(cleaned) == 6:
        return f"{cleaned[:3]}_{cleaned[3:]}"
    return cleaned


def display(pair: str) -> str:
    """Human-facing "EUR/USD" form."""
    return normalize(pair).replace("_", "/")


def to_pips(pair: str, price_delta: float) -> float:
    """Convert a raw price difference into pips."""
    size = pip_size(pair)
    return price_delta / size if size else 0.0


def from_pips(pair: str, pips: float) -> float:
    """Convert a pip count into a raw price difference."""
    return pips * pip_size(pair)


def pip_value_per_unit(
    pair: str, price: float = 1.0, quote_to_usd: float | None = None
) -> float:
    """Value of a one-pip move per unit traded, in USD account terms.

    The exact value is  pip_size × (USD value of one quote-currency unit). When
    `quote_to_usd` is supplied (the USD value of 1 unit of the quote currency)
    this is computed precisely for ALL pairs, including crosses:

        EUR/USD  quote=USD  → quote_to_usd 1.0       → 0.0001
        USD/JPY  quote=JPY  → quote_to_usd 1/USDJPY  → 0.01/USDJPY
        EUR/JPY  quote=JPY  → quote_to_usd 1/USDJPY  → 0.01/USDJPY  (the fix)

    Without `quote_to_usd` it falls back to a price-only approximation that is
    correct for USD-quoted and USD-based pairs but WRONG for crosses (returns the
    raw quote-currency pip size). That legacy path is only safe in the backtest,
    where the same pip_value is used for both sizing and P&L so the error cancels;
    the live engine must always pass `quote_to_usd` or it will mis-size crosses
    by the cross rate (e.g. ~160× too small for EUR/JPY).
    """
    if quote_to_usd is not None and quote_to_usd > 0:
        return pip_size(pair) * quote_to_usd

    quote = quote_currency(pair)
    base = base_currency(pair)
    if quote == "USD":
        return pip_size(pair)
    if base == "USD" and price > 0:
        return pip_size(pair) / price
    # Cross pair, no conversion supplied — legacy approximation (backtest only).
    return pip_size(pair)
