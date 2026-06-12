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
