"""Default ticker universe used by the screener endpoints.

DEFAULT_UNIVERSE covers the S&P 500 broadly (plus popular ETFs and high-beta
names) so the auto-trader's first-pass scan sees the full US large-cap market,
not just a short hand-picked list.

Users can also run the screener against any custom list of symbols via the
`symbols` query parameter - the app supports any ticker on Yahoo Finance.
"""

DEFAULT_UNIVERSE: list[str] = [
    # === INFORMATION TECHNOLOGY ===
    # Semiconductors
    "NVDA", "AVGO", "AMD", "QCOM", "TXN", "INTC", "MU", "AMAT", "LRCX", "KLAC",
    "MCHP", "MPWR", "ON", "MRVL", "SWKS", "TER", "KEYS", "ENPH", "GRMN",
    # Software - infrastructure & cloud
    "MSFT", "ORCL", "CRM", "ADBE", "NOW", "INTU", "CDNS", "SNPS", "ANSS",
    "ADSK", "WDAY", "TEAM", "DDOG", "NET", "CRWD", "PANW", "FTNT",
    "ZS", "OKTA", "VEEV", "HUBS", "PCTY", "PAYC", "GWRE", "MDB", "ESTC",
    "SNOW", "PLTR", "PTC",
    # IT services & consulting
    "ACN", "CTSH", "IT", "EPAM", "LDOS", "SAIC", "BAH", "CDW", "GEN",
    "AKAM", "VRSN", "JKHY",
    # Payments & fintech
    "V", "MA", "PYPL", "FIS", "FISV", "GPN", "ADP", "PAYX",
    # Hardware, networking & storage
    "AAPL", "IBM", "CSCO", "ANET", "HPQ", "HPE", "STX", "WDC", "NTAP",
    "JNPR", "FFIV", "ZBRA", "TDY", "TDG",

    # === COMMUNICATION SERVICES ===
    "GOOGL", "META", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR",
    "FOXA", "FOX", "OMC", "IPG", "LYV", "MTCH", "WBD", "PARA", "NWSA",
    "TTWO", "EA",

    # === CONSUMER DISCRETIONARY ===
    # E-commerce & retail
    "AMZN", "HD", "TGT", "LOW", "BBY", "DG", "DLTR", "ROST", "TJX", "ULTA",
    "ETSY", "EBAY", "W", "CHWY", "RH",
    # Restaurants & leisure
    "MCD", "SBUX", "CMG", "YUM", "DRI", "HLT", "MAR", "MGM", "WYNN", "LVS",
    "EXPE", "BKNG", "ABNB", "RCL", "CCL", "NCLH", "DKNG",
    # Autos & parts
    "TSLA", "GM", "F", "BWA", "APTV", "VC", "LEA", "LKQ", "AN", "KMX", "PAG",
    # Apparel & brands
    "NKE", "VFC", "PVH", "TPR", "RL", "HAS", "MAT",
    # Homebuilders & home improvement
    "DHI", "LEN", "PHM", "NVR", "TOL", "POOL",
    # Other
    "ORLY", "AZO", "UBER", "SHOP",

    # === CONSUMER STAPLES ===
    "WMT", "PG", "KO", "PEP", "COST", "PM", "MO", "MDLZ", "KHC", "GIS",
    "K", "CAG", "SJM", "HRL", "CPB", "CL", "CHD", "CLX", "TSN", "KR",
    "SYY", "BG", "ADM",

    # === HEALTH CARE ===
    # Pharma & biotech
    "JNJ", "LLY", "ABBV", "MRK", "PFE", "BMY", "AMGN", "GILD", "REGN",
    "VRTX", "BIIB", "MRNA", "ILMN", "ALNY", "EXAS", "RARE",
    # Medical devices
    "ABT", "MDT", "SYK", "BSX", "EW", "ZBH", "BDX", "BAX", "RMD", "HOLX",
    "PODD", "DXCM", "ALGN", "ISRG", "IDXX",
    # Life sciences & tools
    "TMO", "DHR", "MTD", "WAT", "A", "IQV", "CRL",
    # Managed care & distribution
    "UNH", "CVS", "CI", "HUM", "MOH", "CNC", "ELV", "MCK", "ABC", "CAH",
    "HCA", "DVA", "HSIC", "GEHC",

    # === FINANCIALS ===
    # Banks
    "JPM", "BAC", "WFC", "C", "USB", "MTB", "FITB", "KEY", "HBAN", "RF",
    "CFG", "COF", "SYF", "DFS", "ALLY",
    # Investment banks & brokers
    "GS", "MS", "SCHW", "AMP",
    # Insurance
    "BRK-B", "MET", "PRU", "AFL", "AIG", "CB", "TRV", "ALL", "PGR", "HIG",
    "WTW", "AON", "MMC", "AJG", "CINF", "GL", "L", "RE", "RNR", "MKL", "ACGL",
    # Asset managers & exchanges
    "BLK", "BX", "KKR", "APO", "CG", "SPGI", "MCO", "ICE", "CME", "CBOE",
    "MSCI", "NDAQ", "FDS", "MKTX", "AXP",

    # === ENERGY ===
    "XOM", "CVX", "COP", "EOG", "OXY", "MPC", "VLO", "PSX", "SLB", "HAL",
    "BKR", "FANG", "DVN", "HES", "APA", "MRO", "EQT", "CTRA",
    "OKE", "WMB", "KMI", "TRGP",

    # === INDUSTRIALS ===
    # Aerospace & defense
    "BA", "LMT", "RTX", "NOC", "GD", "HII", "HEI", "TDG", "AXON",
    # Machinery & equipment
    "CAT", "DE", "ETN", "EMR", "ROK", "AME", "PH", "DOV", "IR", "IEX",
    "XYL", "ROP", "FTV", "GNRC", "TT", "CARR", "OTIS", "GE", "HON",
    "MMM", "ITW", "NDSN", "IDEX", "TRMB", "WAB",
    # Transportation
    "UPS", "FDX", "DAL", "UAL", "LUV", "ALK", "EXPD", "CHRW", "XPO",
    "JBHT", "ODFL", "SAIA",
    # Services
    "FAST", "GWW", "RSG", "WM", "CTAS", "CPRT", "FLR", "J", "PWR",

    # === MATERIALS ===
    "LIN", "APD", "SHW", "PPG", "ECL", "DD", "DOW", "NEM", "FCX", "FMC",
    "CF", "MOS", "NUE", "STLD", "RS", "ATI", "MLM", "VMC", "ALB",
    "AMCR", "SEE", "IP", "PKG", "CCK", "BLL", "WPM",

    # === UTILITIES ===
    "NEE", "DUK", "SO", "D", "SRE", "AEP", "XEL", "PCG", "EIX", "ETR",
    "FE", "PPL", "ED", "ES", "DTE", "CMS", "NI", "AEE", "WEC", "LNT", "AWK",

    # === REAL ESTATE ===
    # Cell towers & data centers
    "AMT", "CCI", "SBA", "EQIX", "DLR", "IRM",
    # Industrial & logistics REITs
    "PLD", "STAG", "LXP", "REXR",
    # Retail REITs
    "SPG", "O", "NNN", "KIM", "REG", "FRT", "WPC",
    # Residential REITs
    "AVB", "EQR", "UDR", "ESS", "MAA", "CPT",
    # Healthcare & specialty REITs
    "WELL", "VTR", "ARE", "PSA", "EXR", "CUBE",
    # Gaming REITs
    "VICI", "GLPI",

    # === BROAD-MARKET ETFs ===
    "SPY", "QQQ", "DIA", "IWM", "VTI", "VOO",
    # Sector ETFs
    "XLF", "XLE", "XLK", "XLV", "XLI", "XLB", "XLU", "XLP", "XLY", "XLRE",
    # Commodity ETFs
    "GLD", "SLV", "TLT",

    # === HIGH-BETA / MOMENTUM NAMES ===
    "COIN", "MSTR", "MARA", "RIOT", "SQ", "SOFI", "RIVN", "LCID", "NIO",
    "AI", "IONQ", "RKLB", "ACHR", "PLUG", "AFRM", "UPST", "SMCI", "ARM",
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
