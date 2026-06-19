import Foundation

// MARK: - Auto-Trader Config

struct AutoTraderConfig: Codable, Hashable {
    var riskPct: Double
    var rrRatio: Double
    var minStopPips: Double
    var maxStopPips: Double
    var maxPositions: Int
    var maxTradesPerDay: Int
    var dailyLossLimitPct: Double
    var minConfidence: Double
    var maxSpreadPips: Double
    var sessionFilter: Bool
    var scanIntervalMinutes: Int
    var pairs: [String]
}

// MARK: - Auto-Trader Trade Record

struct AutoTradeRecord: Codable, Identifiable, Hashable {
    var pair: String
    var side: String          // "long" | "short"
    var units: Int
    var entry: Double
    var stop: Double
    var target: Double
    var openedAt: String
    var tradeId: String
    var status: String        // "open" | "closed"
    var closedAt: String?
    var realizedPl: Double?

    var id: String { "\(pair)-\(tradeId)" }
    var isOpen: Bool { status == "open" }
    var isLong: Bool { side == "long" }

    var display: String { pair.replacingOccurrences(of: "_", with: "/") }

    var stopPips: Double {
        let ps = pair.hasSuffix("JPY") ? 0.01 : 0.0001
        return abs(entry - stop) / ps
    }

    var targetPips: Double {
        let ps = pair.hasSuffix("JPY") ? 0.01 : 0.0001
        return abs(target - entry) / ps
    }
}

// MARK: - Auto-Trader Status

struct AutoTraderStatus: Codable, Hashable {
    var running: Bool
    var halted: Bool
    var haltReason: String
    var environment: String
    var sessionDate: String?
    var startOfDayBalance: Double?
    var dailyPl: Double
    var tradesToday: Int
    var openPositions: Int
    var consecutiveLosses: Int
    var riskScale: Double
    var config: AutoTraderConfig
    var recentTrades: [AutoTradeRecord]

    var statusLabel: String {
        if halted { return "Halted" }
        if running { return "Running" }
        return "Stopped"
    }

    var dailyPlPct: Double {
        guard let start = startOfDayBalance, start > 0 else { return 0 }
        return dailyPl / start * 100
    }
}

// MARK: - Start request helpers (built in ViewModel, sent as JSON)

struct AutoTraderStartRequest: Codable {
    var token: String
    var accountId: String
    var environment: String
    var liveTradingAcknowledged: Bool
    var riskPct: Double?
    var maxPositions: Int?
    var maxTradesPerDay: Int?
    var dailyLossLimitPct: Double?
    var rrRatio: Double?
    var maxSpreadPips: Double?
    var minConfidence: Double?
    var sessionFilter: Bool?
    var pairs: [String]?
}

// MARK: - Config patch (live-tune a running bot)

struct AutoTraderConfigPatch: Codable {
    var riskPct: Double?
    var maxPositions: Int?
    var maxTradesPerDay: Int?
    var dailyLossLimitPct: Double?
    var rrRatio: Double?
    var maxSpreadPips: Double?
    var minConfidence: Double?
    var sessionFilter: Bool?
}
