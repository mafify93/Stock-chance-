import Foundation

// MARK: - Auto-Trader Config

struct AutoTraderConfig: Codable, Hashable {
    var riskPct: Double
    var rrRatio: Double
    var minStopPips: Double
    var maxStopPips: Double
    var maxPositions: Int
    var maxTradesPerDay: Int
    var minConfidence: Double
    var maxSpreadPips: Double
    var sessionFilter: Bool
    var scanIntervalMinutes: Int
    var pairs: [String]
    // New fields — optional so the app degrades gracefully with an older backend
    var useLondonBreakout: Bool?
    var londonBreakoutPairs: [String]?
    var useAiLearner: Bool?
    var aiMinWinProb: Double?
    var useIctSweep: Bool?
    var useOrb: Bool?
    var useSilverBullet: Bool?
    var useOrderBlocks: Bool?
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

// MARK: - AI Learner Stats

struct LearnerStats: Codable {
    var totalTradesObserved: Int
    var winRate: Double?
    var modelActive: Bool
    var tradesUntilActive: Int
    var featureImportances: [String: Double]?

    var winRatePct: Double { (winRate ?? 0) * 100 }
}

// MARK: - Backtest models

struct BacktestRequest: Codable {
    var token: String
    var accountId: String
    var environment: String
    var pairs: [String]?
    var bars: Int
    var spreadPips: Double
    var startingNav: Double
    var riskPct: Double?
    var rrRatio: Double?
    var minConfidence: Double?
    var sessionFilter: Bool?
    var maxTradesPerDay: Int?
    var minStopPips: Double?
    var maxStopPips: Double?
}

struct BacktestStatsModel: Codable, Identifiable {
    var pair: String
    var trades: Int
    var wins: Int
    var losses: Int
    var winRate: Double
    var grossPips: Double
    var spreadPaidPips: Double
    var netPips: Double
    var avgWinPips: Double
    var avgLossPips: Double
    var expectancyPips: Double
    var profitFactor: Double
    var netPnlUsd: Double
    var returnPct: Double
    var maxDrawdownPct: Double
    var endingNav: Double

    var id: String { pair }
    var winRatePct: Double { winRate * 100 }
}

struct BacktestTradeModel: Codable, Identifiable {
    var pair: String
    var side: String
    var entryTime: String
    var exitTime: String
    var entry: Double
    var exit: Double
    var stop: Double
    var target: Double
    var units: Int
    var outcome: String
    var grossPips: Double
    var netPips: Double
    var pnlUsd: Double
    var confidence: Double

    var id: String { "\(pair)-\(entryTime)" }
    var isWin: Bool { outcome == "win" }
}

struct BacktestResult: Codable {
    var startingNav: Double
    var endingNav: Double
    var overall: BacktestStatsModel
    var perPair: [BacktestStatsModel]
    var tradeCount: Int
    var trades: [BacktestTradeModel]
    var errors: [String]
    var barsPerPair: Int

    var returnPct: Double {
        guard startingNav > 0 else { return 0 }
        return (endingNav - startingNav) / startingNav * 100
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
    var rrRatio: Double?
    var maxSpreadPips: Double?
    var minConfidence: Double?
    var sessionFilter: Bool?
    var useLondonBreakout: Bool?
    var useAiLearner: Bool?
    var aiMinWinProb: Double?
    var useIctSweep: Bool?
    var useOrb: Bool?
    var useSilverBullet: Bool?
    var useOrderBlocks: Bool?
}
