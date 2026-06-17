import Foundation
import SwiftUI

// MARK: - Search

struct SearchResult: Codable, Identifiable, Hashable {
    var symbol: String
    var name: String?
    var exchange: String?
    var type: String?
    var sector: String?

    var id: String { symbol }
}

// MARK: - Quote

struct Quote: Codable, Hashable {
    var symbol: String
    var price: Double
    var previousClose: Double?
    var change: Double?
    var changePercent: Double?
    var dayHigh: Double?
    var dayLow: Double?
    var open: Double?
    var volume: Double?
    var marketCap: Double?
    var currency: String?
    var exchange: String?
    var fiftyDayAverage: Double?
    var twoHundredDayAverage: Double?
    var yearHigh: Double?
    var yearLow: Double?
}

// MARK: - Candle (chart data)

struct Candle: Codable, Identifiable, Hashable {
    var date: String
    var open: Double
    var high: Double
    var low: Double
    var close: Double
    var volume: Double

    var id: String { date }

    var dateValue: Date {
        ISO8601DateFormatter.flexible.date(from: date) ?? Date()
    }
}

extension ISO8601DateFormatter {
    /// Yahoo timestamps include a timezone offset like "-04:00" but no
    /// fractional seconds; the default formatter requires fractional
    /// seconds to be configured explicitly to avoid returning nil.
    static let flexible: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
}

// MARK: - Signal

enum TradeAction: String, Codable, CaseIterable {
    case strongBuy = "STRONG_BUY"
    case buy = "BUY"
    case hold = "HOLD"
    case sell = "SELL"
    case strongSell = "STRONG_SELL"

    var label: String {
        switch self {
        case .strongBuy: return "Strong Buy"
        case .buy: return "Buy"
        case .hold: return "Hold"
        case .sell: return "Sell"
        case .strongSell: return "Strong Sell"
        }
    }

    var shortLabel: String {
        switch self {
        case .strongBuy, .buy: return "BUY"
        case .hold: return "HOLD"
        case .sell, .strongSell: return "SELL"
        }
    }
}

struct AnalystOutlook: Codable, Hashable {
    var recommendationKey: String?
    var targetMeanPrice: Double?
    var targetHighPrice: Double?
    var targetLowPrice: Double?
    var numberOfAnalystOpinions: Int?
}

struct SignalLevels: Codable, Hashable {
    var suggestedEntry: Double?
    var stopLoss: Double?
    var takeProfit: Double?
    var suggestedExit: Double?
    var stopLossShort: Double?
    var takeProfitShort: Double?
    var riskReward: Double?
}

struct SignalIndicators: Codable, Hashable {
    var rsi14: Double?
    var macd: Double?
    var macdSignal: Double?
    var sma50: Double?
    var sma200: Double?
    var bbUpper: Double?
    var bbLower: Double?
    var stochK: Double?
    var stochD: Double?
    var adx14: Double?
    var atr14: Double?
}

struct SignalResponse: Codable, Hashable {
    var symbol: String
    var action: TradeAction
    var score: Double
    var confidence: Double
    var price: Double
    var reasons: [String]
    var indicators: SignalIndicators
    var levels: SignalLevels
    var analyst: AnalystOutlook?
    var ml: MLPrediction?
    var disclaimer: String
}

// MARK: - AI analysis (ML model + optional LLM analyst)

/// A machine-learning model's prediction of whether the price will be
/// higher in `horizonDays` trading days, expressed as a -1..+1 score
/// alongside the rule-based signal. `nil` on `SignalResponse`/
/// `AIAnalysisResponse` if no trained model is available on the backend.
struct MLPrediction: Codable, Hashable {
    var probabilityUp: Double
    var score: Double
    var action: TradeAction
    var confidence: Double
    var horizonDays: Int
    var modelVersion: String?
}

struct SignalSummary: Codable, Hashable {
    var action: TradeAction
    var score: Double
    var confidence: Double
    var price: Double
    var reasons: [String]
}

/// A short plain-English take from an LLM, generated server-side if
/// `ANTHROPIC_API_KEY` is configured on the backend.
struct LLMAnalysis: Codable, Hashable {
    var action: TradeAction // BUY | SELL | HOLD
    var confidence: Double
    var summary: String
    var model: String
}

/// Combines the rule-based signal, ML prediction, and optional LLM take into
/// one `combinedAction` / `combinedConfidence`.
struct AIAnalysisResponse: Codable, Hashable {
    var symbol: String
    var price: Double
    var signal: SignalSummary
    var ml: MLPrediction?
    var llm: LLMAnalysis?
    var llmConfigured: Bool
    var combinedAction: TradeAction // BUY | SELL | HOLD
    var combinedConfidence: Double
    var disclaimer: String
}

// MARK: - AI Auto-Trader

/// Request body for updating the AI Auto-Trader configuration. Omit
/// `alpacaApiKeyId`/`alpacaApiSecretKey` (leave `nil`) to keep previously
/// saved credentials unchanged.
struct AutoTraderConfigRequest: Encodable {
    var enabled: Bool
    var broker: String = "alpaca" // "alpaca" | "questrade"
    var symbols: [String]
    // When true the engine ignores `symbols` and picks its own candidates.
    var autoSelect: Bool = false
    var autoSelectCount: Int = 5
    var maxOpenPositions: Int = 5
    var minConfidence: Double
    var maxPositionValue: Double
    var maxDailyTrades: Int
    var pollIntervalMinutes: Int
    var environment: String // "paper" | "live" (Alpaca only - Questrade is always real money)
    var confirmedRealMoney: Bool
    var alpacaApiKeyId: String?
    var alpacaApiSecretKey: String?
    var questradeRefreshToken: String?
    var questradeAccountNumber: String?
    var useIntradaySignals: Bool = true
    var stopLossPct: Double = 1.5
    var trailingStopPct: Double = 1.0
    var maxDailyLossPct: Double = 5.0
    var requireMultiTimeframe: Bool = false
    var useInsiderSignal: Bool = true
    var useEarningsSentiment: Bool = false
}

struct AutoTraderConfig: Hashable {
    var enabled: Bool
    var broker: String // "alpaca" | "questrade"
    var symbols: [String]
    var autoSelect: Bool
    var autoSelectCount: Int
    var maxOpenPositions: Int
    var minConfidence: Double
    var maxPositionValue: Double
    var maxDailyTrades: Int
    var pollIntervalMinutes: Int
    var environment: String // "paper" | "live"
    var confirmedRealMoney: Bool
    var alpacaConfigured: Bool
    var questradeConfigured: Bool
    var useIntradaySignals: Bool
    var stopLossPct: Double
    var trailingStopPct: Double
    var maxDailyLossPct: Double
    var requireMultiTimeframe: Bool
    var useInsiderSignal: Bool
    var useEarningsSentiment: Bool
}

extension AutoTraderConfig: Codable {
    enum CodingKeys: String, CodingKey {
        case enabled, broker, symbols, autoSelect, autoSelectCount, maxOpenPositions
        case minConfidence, maxPositionValue, maxDailyTrades, pollIntervalMinutes
        case environment, confirmedRealMoney, alpacaConfigured, questradeConfigured
        case useIntradaySignals, stopLossPct, trailingStopPct, maxDailyLossPct
        case requireMultiTimeframe, useInsiderSignal, useEarningsSentiment
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        enabled = try c.decode(Bool.self, forKey: .enabled)
        broker = try c.decode(String.self, forKey: .broker)
        symbols = try c.decode([String].self, forKey: .symbols)
        autoSelect = try c.decode(Bool.self, forKey: .autoSelect)
        autoSelectCount = try c.decode(Int.self, forKey: .autoSelectCount)
        maxOpenPositions = try c.decode(Int.self, forKey: .maxOpenPositions)
        minConfidence = try c.decode(Double.self, forKey: .minConfidence)
        maxPositionValue = try c.decode(Double.self, forKey: .maxPositionValue)
        maxDailyTrades = try c.decode(Int.self, forKey: .maxDailyTrades)
        pollIntervalMinutes = try c.decode(Int.self, forKey: .pollIntervalMinutes)
        environment = try c.decode(String.self, forKey: .environment)
        confirmedRealMoney = try c.decode(Bool.self, forKey: .confirmedRealMoney)
        alpacaConfigured = try c.decode(Bool.self, forKey: .alpacaConfigured)
        questradeConfigured = try c.decode(Bool.self, forKey: .questradeConfigured)
        // New fields — fall back to safe defaults when talking to an older backend
        useIntradaySignals = try c.decodeIfPresent(Bool.self, forKey: .useIntradaySignals) ?? true
        stopLossPct = try c.decodeIfPresent(Double.self, forKey: .stopLossPct) ?? 1.5
        trailingStopPct = try c.decodeIfPresent(Double.self, forKey: .trailingStopPct) ?? 1.0
        maxDailyLossPct = try c.decodeIfPresent(Double.self, forKey: .maxDailyLossPct) ?? 5.0
        requireMultiTimeframe = try c.decodeIfPresent(Bool.self, forKey: .requireMultiTimeframe) ?? false
        useInsiderSignal = try c.decodeIfPresent(Bool.self, forKey: .useInsiderSignal) ?? true
        useEarningsSentiment = try c.decodeIfPresent(Bool.self, forKey: .useEarningsSentiment) ?? false
    }
}

/// One evaluation result from the auto-trader - a HOLD, a skipped trade with
/// the reason why, or an executed order.
struct AutoTraderDecision: Codable, Identifiable, Hashable {
    var timestamp: String
    var symbol: String
    var action: String // "BUY" | "SELL" | "HOLD"
    var combinedConfidence: Double
    var executed: Bool
    var reason: String
    var orderId: String?

    var id: String { "\(timestamp)-\(symbol)" }

    var date: Date {
        ISO8601DateFormatter.flexible.date(from: timestamp) ?? Date()
    }
}

struct AutoTraderStatus: Codable, Hashable {
    var config: AutoTraderConfig
    var lastRunAt: String?
    var tradesToday: Int
    var decisions: [AutoTraderDecision]
    var disclaimer: String
}

struct AutoTraderPosition: Codable, Identifiable, Hashable {
    var symbol: String
    var entryPrice: Double
    var currentPrice: Double?
    var pnlPct: Double?
    var pnlDollar: Double?

    var id: String { symbol }
}

struct SellAllResponse: Codable {
    var sold: [String]
    var errors: [[String: String]]
    var message: String
}

// MARK: - Tonight's Picks (nightly AI deep-research scan)

/// A single "Tonight's Picks" recommendation: a symbol, an action (BUY or
/// WATCH), the AI's confidence, the news catalyst it found, and a short plan
/// for the next session.
struct NightPick: Codable, Identifiable, Hashable {
    var symbol: String
    var action: String // "BUY" | "WATCH"
    var confidence: Double
    var catalyst: String
    var plan: String

    var id: String { symbol }
}

/// The latest completed nightly deep-research scan.
struct NightScanResult: Codable, Hashable {
    var generatedAt: String
    var summary: String
    var picks: [NightPick]
    var model: String
    var disclaimer: String

    var date: Date {
        ISO8601DateFormatter.flexible.date(from: generatedAt) ?? Date()
    }
}

/// Whether the nightly scan is configured, when it last/next runs, and its
/// latest result (if any).
struct NightScanStatus: Codable, Hashable {
    var configured: Bool
    var lastRunAt: String?
    var nextRunAt: String?
    var result: NightScanResult?
}

// MARK: - Backtest

struct BacktestTrade: Codable, Identifiable, Hashable {
    var entryDate: String
    var exitDate: String
    var entryPrice: Double
    var exitPrice: Double
    var profitLoss: Double
    var profitLossPct: Double
    var exitReason: String // "SELL" | "STRONG_SELL" | "END_OF_PERIOD"

    var id: String { "\(entryDate)-\(exitDate)" }
}

struct BacktestResponse: Codable, Hashable {
    var symbol: String
    var startDate: String
    var endDate: String
    var startPrice: Double
    var endPrice: Double
    var initialCapital: Double
    var finalValue: Double
    var totalReturnPct: Double
    var buyHoldReturnPct: Double
    var tradeCount: Int
    var winCount: Int
    var winRatePct: Double
    var trades: [BacktestTrade]
    var disclaimer: String
}

// MARK: - Watchlist alerts

/// User-configured price/signal alert for a watched symbol. Removed from
/// `WatchlistAlertStore` entirely once all fields are back to their default
/// (no-op) state.
struct WatchlistAlert: Codable, Hashable {
    var symbol: String
    var priceAbove: Double?
    var priceBelow: Double?
    var notifyOnSignalChange: Bool = false
    /// The signal action last observed for this symbol, used to detect a
    /// change since persisted state survives app relaunches and background
    /// refreshes.
    var lastSignalAction: TradeAction?

    var isActive: Bool {
        priceAbove != nil || priceBelow != nil || notifyOnSignalChange
    }
}

// MARK: - Trade journal

/// A single logged trade - either a real broker order or a manually-tracked
/// "I Bought This" / "Sold" entry - used to compute win rate and realized
/// P/L over time.
struct JournalEntry: Codable, Identifiable, Hashable {
    var id: UUID = UUID()
    var symbol: String
    var side: String // "buy" | "sell"
    var quantity: Double
    var price: Double
    var timestamp: Date
    var source: String // "paper" | "live-alpaca" | "questrade" | "manual"
    var realizedPL: Double?
}

// MARK: - Screener

struct ScreenerItem: Codable, Identifiable, Hashable {
    var symbol: String
    var action: TradeAction
    var score: Double
    var confidence: Double
    var price: Double
    var changePercent: Double?

    var id: String { symbol }
}

struct ScreenerResponse: Codable, Hashable {
    var generatedAt: String
    var buy: [ScreenerItem]
    var sell: [ScreenerItem]
    var hold: [ScreenerItem]
}

// MARK: - Live updates (WebSocket)

struct LiveUpdate: Codable {
    var symbol: String
    var quote: Quote?
    var signal: LiveSignal?
    var error: String?
}

struct LiveSignal: Codable {
    var action: TradeAction
    var score: Double
    var confidence: Double
    var reasons: [String]
    var levels: SignalLevels
}

// MARK: - Day trading (same-day only)

enum MarketSessionStatus: String, Codable {
    case preMarket = "pre_market"
    case open = "open"
    case afterHours = "after_hours"
    case closed = "closed"

    var label: String {
        switch self {
        case .preMarket: return "Pre-Market"
        case .open: return "Market Open"
        case .afterHours: return "After Hours"
        case .closed: return "Market Closed"
        }
    }

    var color: Color {
        switch self {
        case .open: return Theme.profit
        case .preMarket, .afterHours: return Theme.gold
        case .closed: return Theme.neutral
        }
    }
}

struct MarketSession: Codable, Hashable {
    var status: MarketSessionStatus
    var nowEt: String
    var minutesToClose: Int?
    var minutesToOpen: Int?
    var isWeekday: Bool
}

enum DayAction: String, Codable {
    case dayBuy = "DAY_BUY"
    case daySell = "DAY_SELL"
    case dayHold = "DAY_HOLD"

    var label: String {
        switch self {
        case .dayBuy: return "Buy Now"
        case .daySell: return "Sell Now"
        case .dayHold: return "Hold / Wait"
        }
    }

    var color: Color {
        switch self {
        case .dayBuy: return Theme.profit
        case .daySell: return Theme.loss
        case .dayHold: return Theme.gold
        }
    }

    var systemImage: String {
        switch self {
        case .dayBuy: return "arrow.up.circle.fill"
        case .daySell: return "arrow.down.circle.fill"
        case .dayHold: return "hourglass"
        }
    }
}

enum DayAlert: String, Codable {
    case takeProfit = "TAKE_PROFIT_ZONE"
    case stopLoss = "STOP_LOSS_ZONE"
    case eodExit = "EOD_EXIT"

    var label: String {
        switch self {
        case .takeProfit: return "Take-Profit Zone - consider selling"
        case .stopLoss: return "Stop-Loss Zone - consider cutting losses"
        case .eodExit: return "Market closing soon - sell now"
        }
    }

    var color: Color {
        switch self {
        case .takeProfit: return Theme.profit
        case .stopLoss, .eodExit: return Theme.loss
        }
    }
}

struct DaySignalResponse: Codable, Hashable {
    var symbol: String
    var action: DayAction
    var confidence: Double
    var price: Double
    var vwap: Double?
    var sessionOpen: Double
    var sessionHigh: Double
    var sessionLow: Double
    var changeFromOpenPct: Double
    var reasons: [String]
    var entry: Double?
    var target: Double?
    var stop: Double?
    var suspectedProfitPct: Double?
    var suspectedProfitAmount: Double?
    var alert: DayAlert?
    var session: MarketSession
    var disclaimer: String
}

struct DayLiveUpdate: Codable {
    var symbol: String
    var signal: DaySignalResponse?
    var error: String?
}

enum MorningAction: String, Codable {
    case buyAtOpen = "BUY_AT_OPEN"
    case watchDip = "WATCH_DIP"
    case avoid = "AVOID"
    case neutral = "NEUTRAL"

    var label: String {
        switch self {
        case .buyAtOpen: return "Buy at Open"
        case .watchDip: return "Watch for Dip"
        case .avoid: return "Avoid Today"
        case .neutral: return "Neutral"
        }
    }

    var color: Color {
        switch self {
        case .buyAtOpen: return Theme.profit
        case .watchDip: return Theme.gold
        case .avoid: return Theme.loss
        case .neutral: return Theme.neutral
        }
    }
}

struct MorningCandidate: Codable, Identifiable, Hashable {
    var symbol: String
    var action: MorningAction
    var price: Double
    var gapPercent: Double?
    var dataMode: String
    var dailyTrend: TradeAction
    var dailyScore: Double
    var suspectedProfitPct: Double
    var suspectedProfitAmount: Double
    var plan: String
    var reasons: [String]

    var id: String { symbol }
}

struct MorningScanResponse: Codable, Hashable {
    var generatedAt: String
    var session: MarketSession
    var buyAtOpen: [MorningCandidate]
    var watch: [MorningCandidate]
    var avoid: [MorningCandidate]
    var disclaimer: String
}

// MARK: - Top Pick (combined recommendation)

struct Opportunity: Codable, Identifiable, Hashable {
    var symbol: String
    var action: TradeAction
    var headline: String
    var summary: String
    var opportunityScore: Double
    var confidence: Double
    var price: Double
    var changePercent: Double?
    var entry: Double?
    var target: Double?
    var stop: Double?
    var suspectedProfitPct: Double?
    var suspectedProfitAmount: Double?
    var analystTargetUpsidePct: Double?
    var reasons: [String]

    var id: String { symbol }
}

struct TopPickResponse: Codable, Hashable {
    var generatedAt: String
    var session: MarketSession
    var picks: [Opportunity]
    var disclaimer: String
}

// MARK: - "I bought this" positions

struct Position: Codable, Identifiable, Hashable {
    var id: UUID = UUID()
    var symbol: String
    var entryPrice: Double
    var quantity: Double
    var boughtAt: Date
}

// MARK: - Pre-Market Movers

struct MoverCandidate: Codable, Identifiable, Hashable {
    var symbol: String
    var price: Double
    var changePercent: Double
    var dataMode: String
    var relativeVolume: Double?
    var averageVolume: Double?
    var marketCap: Double?
    var momentumScore: Double
    var dailyTrend: TradeAction
    var riskFlags: [String]
    var reasons: [String]

    var id: String { symbol }
}

enum MoverRiskFlag: String {
    case extremeMove = "EXTREME_MOVE"
    case lowPrice = "LOW_PRICE"
    case lowLiquidity = "LOW_LIQUIDITY"

    var label: String {
        switch self {
        case .extremeMove: return "Extreme Move"
        case .lowPrice: return "Low Price"
        case .lowLiquidity: return "Low Liquidity"
        }
    }
}

struct MoversResponse: Codable, Hashable {
    var generatedAt: String
    var session: MarketSession
    var movers: [MoverCandidate]
    var disclaimer: String
}

// MARK: - Broker (Alpaca paper trading)

struct BrokerAccount: Codable, Hashable {
    var accountNumber: String?
    var status: String?
    var buyingPower: Double?
    var cash: Double?
    var portfolioValue: Double?
    var equity: Double?
    var currency: String?
    var patternDayTrader: Bool?
    var tradingBlocked: Bool?
}

struct BrokerPosition: Codable, Identifiable, Hashable {
    var symbol: String
    var quantity: Double
    var avgEntryPrice: Double
    var currentPrice: Double?
    var marketValue: Double?
    var unrealizedPl: Double?
    var unrealizedPlpc: Double?

    var id: String { symbol }
}

struct BrokerOrderRequest: Encodable {
    var symbol: String
    var quantity: Double
    var side: String
    var type: String = "market"
    var timeInForce: String = "day"

    enum CodingKeys: String, CodingKey {
        case symbol, quantity, side, type
        case timeInForce = "time_in_force"
    }
}

struct BrokerOrder: Codable, Hashable {
    var id: String
    var symbol: String?
    var quantity: Double?
    var side: String?
    var type: String?
    var status: String?
    var submittedAt: String?
    var filledAvgPrice: Double?
}

/// Which Alpaca account a broker request targets.
enum BrokerEnvironment: String {
    case paper
    case live
}

// MARK: - Broker (Questrade - LIVE, real money)

struct QuestradeTokenRequest: Encodable {
    var refreshToken: String
}

struct QuestradeAuthResponse: Codable {
    var accessToken: String
    var apiServer: String
    var refreshToken: String
    var expiresIn: Int
    var tokenType: String
}

struct QuestradeAccount: Codable, Identifiable, Hashable {
    var accountNumber: String
    var type: String?
    var status: String?
    var isPrimary: Bool?

    var id: String { accountNumber }
}

struct QuestradeBalances: Codable, Hashable {
    var currency: String?
    var cash: Double?
    var marketValue: Double?
    var totalEquity: Double?
    var buyingPower: Double?
}

struct QuestradePosition: Codable, Identifiable, Hashable {
    var symbol: String
    var quantity: Double
    var avgEntryPrice: Double
    var currentPrice: Double?
    var marketValue: Double?
    var unrealizedPl: Double?

    var id: String { symbol }
}

struct QuestradeSymbol: Codable, Identifiable, Hashable {
    var symbol: String
    var symbolId: Int
    var description: String?

    var id: Int { symbolId }
}

struct QuestradeOrderRequest: Encodable {
    var accountNumber: String
    var symbolId: Int
    var symbol: String
    var quantity: Double
    var side: String // "Buy" | "Sell"
    var orderType: String = "Market"
    var timeInForce: String = "Day"
    var limitPrice: Double?
}

struct QuestradeOrder: Codable, Hashable {
    var id: Int
    var symbol: String?
    var quantity: Double?
    var side: String?
    var type: String?
    var state: String?
    var avgExecPrice: Double?
}

// MARK: - Ask the AI (chat) and Daily AI Briefing

/// Whether an optional AI feature (chat, daily briefing) is configured -
/// i.e. the backend has `ANTHROPIC_API_KEY` set.
struct AIFeatureStatus: Codable, Hashable {
    var configured: Bool
}

/// A holding sent as context to the AI - mirrors `Position`/broker positions
/// but only the fields the AI needs.
struct ChatPosition: Codable, Hashable {
    var symbol: String
    var quantity: Double
    var avgEntryPrice: Double?
}

/// One turn in an "Ask the AI" conversation.
struct ChatMessage: Codable, Identifiable, Hashable {
    var id: UUID = UUID()
    var role: String // "user" | "assistant"
    var content: String

    enum CodingKeys: String, CodingKey {
        case role, content
    }
}

/// Live data sent alongside a chat request so the AI can ground its answer
/// in the user's actual positions and watchlist.
struct AIChatContext: Encodable, Hashable {
    var positions: [ChatPosition]
    var watchlist: [String]
}

struct AIChatRequest: Encodable {
    var messages: [ChatMessage]
    var context: AIChatContext
}

struct AIChatResponse: Decodable, Hashable {
    var reply: String
    var disclaimer: String
}

/// Request body for the Daily AI Briefing - the user's current holdings and
/// watchlist, so the briefing can be personalized.
struct DailyBriefingRequest: Encodable {
    var positions: [ChatPosition]
    var watchlist: [String]
}

struct DailyBriefingResponse: Codable, Hashable {
    var generatedAt: String
    var briefing: String
    var model: String
    var disclaimer: String

    var date: Date {
        ISO8601DateFormatter.flexible.date(from: generatedAt) ?? Date()
    }
}

// MARK: - Analytics Dashboard

struct DailyPerf: Codable, Identifiable {
    var date: String
    var trades: Int
    var pnl: Double
    var wins: Int
    var losses: Int
    var id: String { date }
}

struct AnalyticsResponse: Codable {
    var totalTrades: Int
    var buys: Int
    var sells: Int
    var wins: Int
    var losses: Int
    var winRate: Double
    var totalPnl: Double
    var avgWin: Double
    var avgLoss: Double
    var largestWin: Double
    var largestLoss: Double
    var daily: [DailyPerf]
    var periodDays: Int
}
