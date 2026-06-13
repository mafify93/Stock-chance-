from __future__ import annotations

from pydantic import BaseModel


class SearchResult(BaseModel):
    symbol: str
    name: str | None = None
    exchange: str | None = None
    type: str | None = None
    sector: str | None = None


class Quote(BaseModel):
    symbol: str
    price: float
    previous_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    open: float | None = None
    volume: float | None = None
    market_cap: float | None = None
    currency: str | None = None
    exchange: str | None = None
    fifty_day_average: float | None = None
    two_hundred_day_average: float | None = None
    year_high: float | None = None
    year_low: float | None = None


class Candle(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class AnalystOutlook(BaseModel):
    recommendation_key: str | None = None
    target_mean_price: float | None = None
    target_high_price: float | None = None
    target_low_price: float | None = None
    number_of_analyst_opinions: int | None = None
    recommendations_summary: dict | None = None


class SignalResponse(BaseModel):
    symbol: str
    action: str
    score: float
    confidence: float
    price: float
    reasons: list[str]
    indicators: dict
    levels: dict
    analyst: AnalystOutlook | None = None
    disclaimer: str = (
        "Educational technical-analysis output, not financial advice. "
        "Past performance and indicator patterns do not guarantee future results."
    )


class ScreenerItem(BaseModel):
    symbol: str
    action: str
    score: float
    confidence: float
    price: float
    change_percent: float | None = None


class ScreenerResponse(BaseModel):
    generated_at: str
    buy: list[ScreenerItem]
    sell: list[ScreenerItem]
    hold: list[ScreenerItem]
    errors: dict[str, str] = {}


# --- Day trading (intraday, same-day only) ---------------------------------


class MarketSessionResponse(BaseModel):
    status: str  # "pre_market" | "open" | "after_hours" | "closed"
    now_et: str
    minutes_to_close: int | None = None
    minutes_to_open: int | None = None
    is_weekday: bool = True


class DaySignalResponse(BaseModel):
    symbol: str
    action: str  # "DAY_BUY" | "DAY_SELL" | "DAY_HOLD"
    confidence: float
    price: float
    vwap: float | None = None
    session_open: float
    session_high: float
    session_low: float
    change_from_open_pct: float
    reasons: list[str]
    entry: float | None = None
    target: float | None = None
    stop: float | None = None
    suspected_profit_pct: float | None = None
    suspected_profit_amount: float | None = None
    alert: str | None = None
    session: MarketSessionResponse
    disclaimer: str = (
        "Same-day technical signal based on today's intraday price action. "
        "Not financial advice - intraday trading is high-risk."
    )


class MorningCandidate(BaseModel):
    symbol: str
    action: str  # "BUY_AT_OPEN" | "WATCH_DIP" | "AVOID" | "NEUTRAL"
    price: float
    gap_percent: float | None = None
    data_mode: str
    daily_trend: str
    daily_score: float
    suspected_profit_pct: float
    suspected_profit_amount: float
    plan: str
    reasons: list[str]


class MorningScanResponse(BaseModel):
    generated_at: str
    session: MarketSessionResponse
    buy_at_open: list[MorningCandidate]
    watch: list[MorningCandidate]
    avoid: list[MorningCandidate]
    errors: dict[str, str] = {}
    disclaimer: str = (
        "\"Suspected profit\" is an estimate based on the stock's recent daily volatility (ATR), "
        "not a guarantee. Same-day trading is high-risk - only risk money you can afford to lose."
    )


# --- Top Pick (combined recommendation) -------------------------------------


class Opportunity(BaseModel):
    symbol: str
    action: str  # "STRONG_BUY" | "BUY" | "HOLD" | "SELL" | "STRONG_SELL"
    headline: str
    summary: str
    opportunity_score: float
    confidence: float
    price: float
    change_percent: float | None = None
    entry: float | None = None
    target: float | None = None
    stop: float | None = None
    suspected_profit_pct: float | None = None
    suspected_profit_amount: float | None = None
    analyst_target_upside_pct: float | None = None
    reasons: list[str]


class TopPickResponse(BaseModel):
    generated_at: str
    session: MarketSessionResponse
    picks: list[Opportunity]
    errors: dict[str, str] = {}
    disclaimer: str = (
        "\"Top Pick\" combines the longer-term trend, today's intraday momentum, and analyst "
        "price targets into one ranked idea. It is automated technical analysis, not financial "
        "advice - always do your own research before risking money."
    )


# --- Pre-Market Movers --------------------------------------------------------


class MoverCandidate(BaseModel):
    symbol: str
    price: float
    change_percent: float
    data_mode: str
    relative_volume: float | None = None
    average_volume: float | None = None
    market_cap: float | None = None
    momentum_score: float
    daily_trend: str
    risk_flags: list[str] = []
    reasons: list[str] = []


class MoversResponse(BaseModel):
    generated_at: str
    session: MarketSessionResponse
    movers: list[MoverCandidate]
    errors: dict[str, str] = {}
    disclaimer: str = (
        "\"Pre-Market Movers\" ranks stocks by their overnight price gap and trading volume "
        "relative to their own average - it highlights what's unusually active right now, it "
        "does NOT predict how far a move will go. No algorithm can reliably predict a stock "
        "jumping from $1 to $30 in a day. Extreme gaps and low-liquidity (penny) stocks are "
        "flagged because they carry a much higher risk of sudden, violent reversals - never "
        "chase a big gap without a plan, a stop-loss, and a position size you can afford to lose."
    )


# --- Broker (Alpaca paper trading) -------------------------------------------


class BrokerAccount(BaseModel):
    account_number: str | None = None
    status: str | None = None
    buying_power: float | None = None
    cash: float | None = None
    portfolio_value: float | None = None
    equity: float | None = None
    currency: str | None = None
    pattern_day_trader: bool | None = None
    trading_blocked: bool | None = None


class BrokerPosition(BaseModel):
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float | None = None
    market_value: float | None = None
    unrealized_pl: float | None = None
    unrealized_plpc: float | None = None


class BrokerOrderRequest(BaseModel):
    symbol: str
    quantity: float
    side: str  # "buy" | "sell"
    type: str = "market"
    time_in_force: str = "day"


class BrokerOrder(BaseModel):
    id: str
    symbol: str
    quantity: float | None = None
    side: str | None = None
    type: str | None = None
    status: str | None = None
    submitted_at: str | None = None
    filled_avg_price: float | None = None
