import Foundation

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
