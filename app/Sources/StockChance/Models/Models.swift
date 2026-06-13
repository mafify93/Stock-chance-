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
    var disclaimer: String
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
