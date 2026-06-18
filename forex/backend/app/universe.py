"""Default currency-pair universe used by the screener and scan endpoints.

Forex liquidity is concentrated in a small number of pairs, so unlike an
equity universe (hundreds of tickers) this is a focused, hand-picked set of
the most liquid, tightest-spread pairs - the ones a retail day trader can
actually get filled on without paying a punitive spread.

Users can scan any custom list via the `pairs` query parameter; anything
tradable on OANDA works.
"""

# The 7 "major" pairs - all involve USD and carry the deepest liquidity and
# tightest spreads.
MAJORS: list[str] = [
    "EUR_USD",
    "USD_JPY",
    "GBP_USD",
    "USD_CHF",
    "AUD_USD",
    "USD_CAD",
    "NZD_USD",
]

# "Minor" / cross pairs - no USD, still very liquid. Popular with day traders
# for the larger intraday ranges (especially the GBP and JPY crosses).
MINORS: list[str] = [
    "EUR_GBP",
    "EUR_JPY",
    "GBP_JPY",
    "EUR_CHF",
    "AUD_JPY",
    "EUR_AUD",
    "GBP_CHF",
    "CAD_JPY",
    "NZD_JPY",
    "GBP_AUD",
    "EUR_CAD",
    "AUD_CAD",
    "AUD_NZD",
    "CHF_JPY",
]

# Default universe the screener scans when no explicit list is given.
DEFAULT_UNIVERSE: list[str] = MAJORS + MINORS

# A tighter set for the "Top Pick" / morning scan - the highest-liquidity
# pairs where intraday signals are most reliable.
DAYTRADE_UNIVERSE: list[str] = MAJORS + [
    "EUR_JPY",
    "GBP_JPY",
    "EUR_GBP",
    "AUD_JPY",
]
