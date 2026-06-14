"""Default ticker universe used by the screener endpoints.

This is a curated list of widely-traded US equities and ETFs spanning major
sectors. Users can also run the screener against any custom list of symbols
(e.g. their own watchlist) via the `symbols` query parameter - the app
supports searching and analyzing ANY ticker available on Yahoo Finance, this
list is just a convenient "default scan" set.
"""

DEFAULT_UNIVERSE: list[str] = [
    # Mega-cap tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AVGO", "ORCL", "CRM",
    "ADBE", "AMD", "NFLX", "INTC", "CSCO", "QCOM", "TXN", "IBM", "NOW", "INTU",
    # Finance
    "JPM", "BAC", "WFC", "GS", "MS", "C", "AXP", "BLK", "SCHW", "V",
    "MA", "PYPL",
    # Healthcare
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "BMY",
    # Consumer
    "WMT", "PG", "KO", "PEP", "COST", "HD", "MCD", "NKE", "SBUX", "TGT",
    "DIS", "LOW",
    # Energy & Industrials
    "XOM", "CVX", "COP", "GE", "CAT", "BA", "HON", "UPS", "LMT", "RTX",
    # Communication / Media
    "T", "VZ", "CMCSA", "TMUS",
    # ETFs (broad market & sector)
    "SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "XLF", "XLE", "XLK", "XLV",
    "ARKK", "GLD", "SLV", "TLT",
    # Other popular names
    "UBER", "SHOP", "SQ", "COIN", "PLTR", "SNOW", "ABNB", "RIVN", "F", "GM",
]

# A smaller set of highly liquid, high-volatility names well suited to
# same-day (intraday) trading. Used by the morning scan / day-trading
# screener so the (heavier) pre-market lookups stay fast.
DAYTRADE_UNIVERSE: list[str] = [
    "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "AMZN", "META", "GOOGL", "NFLX", "AVGO",
    "SPY", "QQQ", "IWM", "DIA",
    "COIN", "PLTR", "SOFI", "RIVN", "F", "BAC",
    "MARA", "MSTR", "SMCI", "UBER",
]

# Higher-beta small/mid-cap names that tend to see outsized pre-market gaps
# and volume spikes - used by the "Pre-Market Movers" scan in addition to
# DAYTRADE_UNIVERSE. Still liquid, exchange-listed names (not obscure penny
# stocks) so quotes and volume data are reliable.
EXTENDED_MOVERS_UNIVERSE: list[str] = DAYTRADE_UNIVERSE + [
    "LCID", "NIO", "AI", "IONQ", "RKLB", "ACHR", "JOBY", "CGC", "TLRY",
    "FUBO", "CLSK", "RIOT", "HUT", "BBAI", "SIRI", "PLUG", "DKNG",
    "AFRM", "UPST",
]

# Curated for "Tonight's Picks" (see `app.night_scan`): liquid, heavily-covered
# US-listed stocks/ETFs that regularly have concrete, news-driven catalysts -
# earnings, product launches, partnerships/collaborations, FDA/regulatory
# decisions, analyst calls, and macro events - that can move a stock at the
# next day's open. Deliberately not the same as a user's personal watchlist:
# this is the pool the nightly AI research scan searches for catalysts in.
NIGHT_SCAN_UNIVERSE: list[str] = [
    # Mega-cap tech / AI - frequent product, earnings, and partnership news
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD", "AVGO", "PLTR",
    # High-momentum / AI-adjacent - prone to sharp news-driven moves
    "SMCI", "MSTR", "COIN", "MARA", "RIOT", "SOFI", "RIVN", "LCID", "ARM", "IONQ",
    # Biotech / pharma - FDA decisions, trial readouts
    "MRNA", "PFE", "LLY", "NVO", "AMGN",
    # Consumer / retail - earnings, guidance, product launches
    "NFLX", "DIS", "NKE", "SBUX", "COST", "WMT",
    # Finance - earnings, rate-sensitive news
    "JPM", "GS", "V",
    # Energy - macro/OPEC/earnings driven
    "XOM", "CVX",
    # Broad-market ETFs for macro context
    "SPY", "QQQ",
]
