from __future__ import annotations

from pydantic import BaseModel, Field


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


class MLPrediction(BaseModel):
    probability_up: float
    score: float
    action: str
    confidence: float
    horizon_days: int
    model_version: str | None = None


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
    ml: MLPrediction | None = None
    disclaimer: str = (
        "Educational technical-analysis output, not financial advice. "
        "Past performance and indicator patterns do not guarantee future results."
    )


class BacktestTrade(BaseModel):
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    profit_loss: float
    profit_loss_pct: float
    exit_reason: str  # "SELL" | "STRONG_SELL" | "END_OF_PERIOD"


class BacktestResponse(BaseModel):
    symbol: str
    start_date: str
    end_date: str
    start_price: float
    end_price: float
    initial_capital: float
    final_value: float
    total_return_pct: float
    buy_hold_return_pct: float
    trade_count: int
    win_count: int
    win_rate_pct: float
    trades: list[BacktestTrade]
    disclaimer: str = (
        "Backtest results simulate this app's Buy/Sell signal rules against historical data. "
        "They do not account for fees, slippage or taxes. Past performance does not guarantee "
        "future results."
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


# --- Broker (Questrade - LIVE, real money) -----------------------------------


class QuestradeTokenRequest(BaseModel):
    refresh_token: str


class QuestradeAuthResponse(BaseModel):
    access_token: str
    api_server: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


class QuestradeAccount(BaseModel):
    account_number: str
    type: str | None = None
    status: str | None = None
    is_primary: bool | None = None


class QuestradeBalances(BaseModel):
    currency: str | None = None
    cash: float | None = None
    market_value: float | None = None
    total_equity: float | None = None
    buying_power: float | None = None


class QuestradePosition(BaseModel):
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float | None = None
    market_value: float | None = None
    unrealized_pl: float | None = None


class QuestradeSymbol(BaseModel):
    symbol: str
    symbol_id: int
    description: str | None = None


class QuestradeOrderRequest(BaseModel):
    account_number: str
    symbol_id: int
    symbol: str
    quantity: float
    side: str  # "Buy" | "Sell"
    order_type: str = "Market"
    time_in_force: str = "Day"
    limit_price: float | None = None


class QuestradeOrder(BaseModel):
    id: int
    symbol: str | None = None
    quantity: float | None = None
    side: str | None = None
    type: str | None = None
    state: str | None = None
    avg_exec_price: float | None = None


# --- AI analysis (rule-based signal + ML prediction + optional LLM take) -----


class SignalSummary(BaseModel):
    action: str
    score: float
    confidence: float
    price: float
    reasons: list[str]


class LLMAnalysis(BaseModel):
    action: str  # "BUY" | "SELL" | "HOLD"
    confidence: float
    summary: str
    model: str


class AIAnalysisResponse(BaseModel):
    symbol: str
    price: float
    signal: SignalSummary
    ml: MLPrediction | None = None
    llm: LLMAnalysis | None = None
    llm_configured: bool
    combined_action: str  # "BUY" | "SELL" | "HOLD"
    combined_confidence: float
    disclaimer: str = (
        "Combines a rule-based technical signal, a machine-learning direction "
        "model, and (optionally) an LLM-generated summary into one view. None "
        "of this is financial advice or a guarantee - markets are risky."
    )


# --- AI Auto-Trader (optional, places REAL orders when configured) -----------


class AutoTraderConfigRequest(BaseModel):
    enabled: bool = False
    broker: str = "alpaca"  # "alpaca" | "questrade"
    symbols: list[str] = []
    # When True the engine ignores `symbols` and screens a broad liquid
    # universe each cycle, trading only its highest-conviction candidates.
    auto_select: bool = False
    auto_select_count: int = 5
    max_open_positions: int = 5
    min_confidence: float = 70.0
    max_position_value: float = 100.0
    max_daily_trades: int = 3
    poll_interval_minutes: int = 15
    environment: str = "paper"  # "paper" | "live" (Alpaca only - Questrade is always real money)
    confirmed_real_money: bool = False
    alpaca_api_key_id: str | None = None
    alpaca_api_secret_key: str | None = None
    questrade_refresh_token: str | None = None
    questrade_account_number: str | None = None
    stop_loss_pct: float = 3.0
    max_daily_loss_pct: float = 5.0
    require_multi_timeframe: bool = False
    use_insider_signal: bool = True
    use_earnings_sentiment: bool = False


class AutoTraderConfig(BaseModel):
    enabled: bool
    broker: str
    symbols: list[str]
    auto_select: bool
    auto_select_count: int
    max_open_positions: int
    min_confidence: float
    max_position_value: float
    max_daily_trades: int
    poll_interval_minutes: int
    environment: str
    confirmed_real_money: bool
    alpaca_configured: bool
    questrade_configured: bool
    stop_loss_pct: float = 3.0
    max_daily_loss_pct: float = 5.0
    require_multi_timeframe: bool = False
    use_insider_signal: bool = True
    use_earnings_sentiment: bool = False


class AutoTraderDecision(BaseModel):
    timestamp: str
    symbol: str
    action: str  # "BUY" | "SELL" | "HOLD"
    combined_confidence: float
    executed: bool
    reason: str
    order_id: str | None = None


class AutoTraderStatus(BaseModel):
    config: AutoTraderConfig
    last_run_at: str | None = None
    trades_today: int
    decisions: list[AutoTraderDecision]
    disclaimer: str = (
        "The AI Auto-Trader places REAL orders with REAL money when enabled "
        "with a confirmed Alpaca or Questrade account (Questrade has no paper "
        "mode, so it always requires confirmed_real_money). It is automated "
        "technical analysis, not financial advice, and can lose money. You are "
        "solely responsible for any trades it places - disable it at any time."
    )


# --- Tonight's Picks (nightly AI deep-research scan) -------------------------


class NightPick(BaseModel):
    symbol: str
    action: str  # "BUY" | "WATCH"
    confidence: float
    catalyst: str
    plan: str


class NightScanResult(BaseModel):
    generated_at: str
    summary: str
    picks: list[NightPick]
    model: str
    disclaimer: str = (
        "\"Tonight's Picks\" is speculative, news-driven research generated by "
        "an AI model with live web search - not financial advice and not "
        "guaranteed to be profitable. Recent news (earnings, partnerships, "
        "analyst calls, etc.) does not guarantee a stock will move in the "
        "expected direction. Always do your own research and never risk money "
        "you can't afford to lose."
    )


class NightScanStatus(BaseModel):
    configured: bool
    last_run_at: str | None = None
    next_run_at: str | None = None
    result: NightScanResult | None = None


# --- Ask the AI (chat) and Daily AI Briefing ----------------------------------


class AIFeatureStatus(BaseModel):
    configured: bool


class ChatPosition(BaseModel):
    symbol: str
    quantity: float
    avg_entry_price: float | None = None


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AIChatContext(BaseModel):
    positions: list[ChatPosition] = []
    watchlist: list[str] = []


class AIChatRequest(BaseModel):
    messages: list[ChatMessage]
    context: AIChatContext = Field(default_factory=AIChatContext)


class AIChatResponse(BaseModel):
    reply: str
    disclaimer: str = (
        "AI chat answers are generated from the data shown in the app (your "
        "positions, watchlist, auto-trader activity, and current signals) "
        "plus general knowledge - not financial advice and may be incomplete "
        "or wrong."
    )


class DailyBriefingRequest(BaseModel):
    positions: list[ChatPosition] = []
    watchlist: list[str] = []


class DailyBriefingResponse(BaseModel):
    generated_at: str
    briefing: str
    model: str
    disclaimer: str = (
        "\"Daily Briefing\" is an AI-generated summary of your holdings and "
        "watchlist, produced with live web search - speculative, "
        "research-based commentary, not financial advice."
    )


# --- Analytics Dashboard ------------------------------------------------------


class DailyPerf(BaseModel):
    date: str
    trades: int
    pnl: float
    wins: int
    losses: int


class AnalyticsResponse(BaseModel):
    total_trades: int
    buys: int
    sells: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    daily: list[DailyPerf]
    period_days: int
