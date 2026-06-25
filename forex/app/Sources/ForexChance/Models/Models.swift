import Foundation

// MARK: - Pairs

struct PairInfo: Codable, Identifiable, Hashable {
    var pair: String        // "EUR_USD"
    var display: String     // "EUR/USD"
    var base: String
    var quote: String
    var pipSize: Double
    var category: String    // "major" | "minor"

    var id: String { pair }
}

struct PairQuote: Codable, Hashable {
    var pair: String
    var display: String
    var bid: Double?
    var ask: Double?
    var mid: Double?
    var spreadPips: Double?
    var tradeable: Bool
    var time: String?
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
        // Try fractional-seconds format first (OANDA native), then plain
        // ISO-8601 internet format (pandas isoformat output, no sub-seconds).
        ISO8601DateFormatter.flexibleFractional.date(from: date)
            ?? ISO8601DateFormatter.flexible.date(from: date)
            ?? Date()
    }
}

extension ISO8601DateFormatter {
    static let flexibleFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    static let flexible: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
}

// MARK: - Trade actions

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

    /// Order side: long for buys, short for sells.
    var isBuy: Bool {
        self == .strongBuy || self == .buy
    }
}

enum DayAction: String, Codable {
    case buy = "DAY_BUY"
    case sell = "DAY_SELL"
    case hold = "DAY_HOLD"

    var label: String {
        switch self {
        case .buy: return "Day Buy"
        case .sell: return "Day Sell"
        case .hold: return "Day Hold"
        }
    }

    var isBuy: Bool { self == .buy }
    var isActionable: Bool { self != .hold }
}

// MARK: - Signal

struct SignalLevels: Codable, Hashable {
    var suggestedEntry: Double?
    var stopLoss: Double?
    var takeProfit: Double?
    var stopPips: Double?
    var targetPips: Double?
    var riskReward: Double?
}

struct SignalResponse: Codable, Hashable {
    var pair: String
    var display: String
    var action: String
    var score: Double
    var confidence: Double
    var price: Double
    var reasons: [String]
    var levels: SignalLevels
    var disclaimer: String?

    var tradeAction: TradeAction { TradeAction(rawValue: action) ?? .hold }
}

// MARK: - Screener

struct ScreenerItem: Codable, Identifiable, Hashable {
    var pair: String
    var display: String
    var action: String
    var score: Double
    var confidence: Double
    var price: Double
    var changeFromOpenPips: Double?

    var id: String { pair }
    var tradeAction: TradeAction { TradeAction(rawValue: action) ?? .hold }
}

struct ScreenerResponse: Codable, Hashable {
    var generatedAt: String
    var buy: [ScreenerItem]
    var sell: [ScreenerItem]
    var hold: [ScreenerItem]
    var errors: [String: String]
}

// MARK: - Sessions (the forex trading clock)

struct MarketSession: Codable, Hashable {
    var status: String  // "open" | "closed"
    var nowUtc: String
    var activeSessions: [String]
    var isHighLiquidity: Bool
    var minutesToClose: Int?
    var minutesToOpen: Int?
    var note: String

    var isOpen: Bool { status == "open" }
}

// MARK: - Day signal

struct DaySignalResponse: Codable, Hashable {
    var pair: String
    var display: String
    var action: String
    var confidence: Double
    var price: Double
    var vwap: Double?
    var sessionOpen: Double
    var sessionHigh: Double
    var sessionLow: Double
    var changeFromOpenPips: Double
    var reasons: [String]
    var entry: Double?
    var target: Double?
    var stop: Double?
    var targetPips: Double?
    var stopPips: Double?
    var alert: String?
    var session: MarketSession
    var disclaimer: String?

    var dayAction: DayAction { DayAction(rawValue: action) ?? .hold }
}

// MARK: - Top Pick

struct Opportunity: Codable, Identifiable, Hashable {
    var pair: String
    var display: String
    var action: String
    var headline: String
    var summary: String
    var opportunityScore: Double
    var confidence: Double
    var price: Double
    var changeFromOpenPips: Double?
    var entry: Double?
    var target: Double?
    var stop: Double?
    var targetPips: Double?
    var stopPips: Double?
    var reasons: [String]

    var id: String { pair }
    var tradeAction: TradeAction { TradeAction(rawValue: action) ?? .hold }
}

struct TopPickResponse: Codable, Hashable {
    var generatedAt: String
    var session: MarketSession
    var picks: [Opportunity]
    var errors: [String: String]
}

// MARK: - Broker (OANDA)

struct BrokerAccount: Codable, Hashable {
    var accountId: String?
    var alias: String?
    var currency: String?
    var balance: Double?
    var nav: Double?
    var unrealizedPl: Double?
    var realizedPl: Double?
    var marginUsed: Double?
    var marginAvailable: Double?
    var openTradeCount: Int?
    var openPositionCount: Int?
}

struct BrokerPosition: Codable, Identifiable, Hashable {
    var pair: String
    var display: String
    var side: String   // "long" | "short"
    var units: Double
    var avgPrice: Double
    var currentPrice: Double?
    var unrealizedPl: Double?
    var plPips: Double?

    var id: String { "\(pair)-\(side)" }
    var isLong: Bool { side == "long" }
}

struct BrokerOrderRequest: Codable {
    var pair: String
    var units: Double
    var stopLossPrice: Double?
    var takeProfitPrice: Double?
}

struct BrokerOrder: Codable, Hashable {
    var id: String?
    var pair: String
    var display: String
    var units: Double?
    var side: String?
    var status: String
    var fillPrice: Double?
    var time: String?
    var reason: String?

    var wasFilled: Bool { status == "FILLED" }
}

struct CloseRequest: Codable {
    var pair: String
    var side: String
}

struct CloseResponse: Codable, Hashable {
    var pair: String
    var display: String
    var closed: Bool
    var realizedPl: Double?
    var message: String
}
