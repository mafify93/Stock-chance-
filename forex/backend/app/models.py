from __future__ import annotations

from pydantic import BaseModel


# --- Pairs, quotes, candles ---------------------------------------------------


class PairInfo(BaseModel):
    pair: str          # OANDA form, e.g. "EUR_USD"
    display: str       # "EUR/USD"
    base: str
    quote: str
    pip_size: float
    category: str      # "major" | "minor"


class PairQuote(BaseModel):
    pair: str
    display: str
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    spread_pips: float | None = None
    tradeable: bool = True
    time: str | None = None


class Candle(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


# --- Signals ------------------------------------------------------------------


class SignalResponse(BaseModel):
    pair: str
    display: str
    action: str
    score: float
    confidence: float
    price: float
    reasons: list[str]
    indicators: dict
    levels: dict
    disclaimer: str = (
        "Educational technical-analysis output, not financial advice. Leveraged "
        "forex trading carries a high risk of losing money rapidly."
    )


class ScreenerItem(BaseModel):
    pair: str
    display: str
    action: str
    score: float
    confidence: float
    price: float
    change_from_open_pips: float | None = None


class ScreenerResponse(BaseModel):
    generated_at: str
    buy: list[ScreenerItem]
    sell: list[ScreenerItem]
    hold: list[ScreenerItem]
    errors: dict[str, str] = {}


# --- Sessions (the forex trading clock) ---------------------------------------


class MarketSessionResponse(BaseModel):
    status: str  # "open" | "closed"
    now_utc: str
    active_sessions: list[str] = []
    is_high_liquidity: bool = False
    minutes_to_close: int | None = None
    minutes_to_open: int | None = None
    note: str = ""


# --- Same-day (intraday) signal -----------------------------------------------


class DaySignalResponse(BaseModel):
    pair: str
    display: str
    action: str  # "DAY_BUY" | "DAY_SELL" | "DAY_HOLD"
    confidence: float
    price: float
    vwap: float | None = None
    session_open: float
    session_high: float
    session_low: float
    change_from_open_pips: float
    reasons: list[str]
    entry: float | None = None
    target: float | None = None
    stop: float | None = None
    target_pips: float | None = None
    stop_pips: float | None = None
    alert: str | None = None
    session: MarketSessionResponse
    disclaimer: str = (
        "Same-day technical signal based on recent intraday price action. Not "
        "financial advice - intraday forex trading is high-risk."
    )


# --- Top Pick (combined recommendation) ---------------------------------------


class Opportunity(BaseModel):
    pair: str
    display: str
    action: str
    headline: str
    summary: str
    opportunity_score: float
    confidence: float
    price: float
    change_from_open_pips: float | None = None
    entry: float | None = None
    target: float | None = None
    stop: float | None = None
    target_pips: float | None = None
    stop_pips: float | None = None
    reasons: list[str]


class TopPickResponse(BaseModel):
    generated_at: str
    session: MarketSessionResponse
    picks: list[Opportunity]
    errors: dict[str, str] = {}
    disclaimer: str = (
        "\"Top Pick\" combines the higher-timeframe trend and today's intraday "
        "momentum into one ranked idea. It is automated technical analysis, not "
        "financial advice - always do your own research before risking money."
    )


# --- Broker (OANDA - fxPractice demo or fxTrade live) -------------------------


class BrokerAccount(BaseModel):
    account_id: str | None = None
    alias: str | None = None
    currency: str | None = None
    balance: float | None = None
    nav: float | None = None             # net asset value (balance + unrealized P/L)
    unrealized_pl: float | None = None
    realized_pl: float | None = None
    margin_used: float | None = None
    margin_available: float | None = None
    open_trade_count: int | None = None
    open_position_count: int | None = None


class BrokerPosition(BaseModel):
    pair: str
    display: str
    side: str            # "long" | "short"
    units: float
    avg_price: float
    current_price: float | None = None
    unrealized_pl: float | None = None
    pl_pips: float | None = None


class BrokerOrderRequest(BaseModel):
    pair: str
    units: float         # positive = buy/long, negative = sell/short
    stop_loss_price: float | None = None
    take_profit_price: float | None = None


class BrokerOrder(BaseModel):
    id: str | None = None
    pair: str
    display: str
    units: float | None = None
    side: str | None = None
    status: str          # "FILLED" | "CANCELLED" | ...
    fill_price: float | None = None
    time: str | None = None
    reason: str | None = None


class CloseRequest(BaseModel):
    pair: str
    side: str            # "long" | "short"


class CloseResponse(BaseModel):
    pair: str
    display: str
    closed: bool
    realized_pl: float | None = None
    message: str
