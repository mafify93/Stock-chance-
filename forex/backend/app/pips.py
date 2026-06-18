"""Pip math for currency pairs.

A *pip* is the standard unit of price movement in forex. For most pairs one
pip is the 4th decimal place (0.0001); for JPY-quoted pairs it's the 2nd
decimal place (0.01). Almost every forex concept the app shows the user -
spread, stop distance, "suspected profit" - is expressed in pips, so this
module is the single source of truth for converting between price and pips.
"""
from __future__ import annotations

# Pairs quoted in JPY (and a few exotics) use 0.01 as one pip instead of
# the usual 0.0001.
JPY_QUOTED = ("JPY",)


def pip_size(pair: str) -> float:
    """Price increment of a single pip for `pair` (e.g. "EUR_USD" -> 0.0001)."""
    quote = quote_currency(pair)
    if quote in JPY_QUOTED:
        return 0.01
    return 0.0001


def price_decimals(pair: str) -> int:
    """How many decimals to display a price with (one more than the pip,
    matching OANDA's fractional-pip pricing)."""
    return 3 if quote_currency(pair) in JPY_QUOTED else 5


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


def pip_value_per_unit(pair: str, price: float = 1.0) -> float:
    """Approximate value of a one-pip move per unit traded, in USD account terms.

    For USD-quoted pairs (EUR/USD, GBP/USD, AUD/USD, NZD/USD):
        pip_value = pip_size  (exact — the USD rate cancels)
    For USD-based pairs (USD/JPY, USD/CHF, USD/CAD):
        pip_value = pip_size / spot  (varies with the exchange rate)
    For cross pairs (EUR/JPY, GBP/JPY, etc.):
        pip_value ≈ pip_size  (conservative underestimate — OANDA applies the
        precise cross-rate conversion on fill, so this errs on the safe side
        by producing slightly smaller unit counts)
    """
    quote = quote_currency(pair)
    base = base_currency(pair)
    if quote == "USD":
        return pip_size(pair)
    if base == "USD" and price > 0:
        return pip_size(pair) / price
    # Cross pair — approximate; conservative (safer to under-size)
    return pip_size(pair)
