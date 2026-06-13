import SwiftUI

/// "Sell/Hold Position Coach" - turns the live same-day signal for a symbol
/// into a plain-language Hold / Take Profit / Cut Loss recommendation for a
/// position the user is actually holding, using their real entry price.
enum CoachAction {
    case hold
    case takeProfit
    case cutLoss

    var label: String {
        switch self {
        case .hold: return "Hold"
        case .takeProfit: return "Take Profit"
        case .cutLoss: return "Cut Loss"
        }
    }

    var color: Color {
        switch self {
        case .hold: return Theme.gold
        case .takeProfit: return Theme.profit
        case .cutLoss: return Theme.loss
        }
    }

    var systemImage: String {
        switch self {
        case .hold: return "hourglass"
        case .takeProfit: return "checkmark.seal.fill"
        case .cutLoss: return "exclamationmark.octagon.fill"
        }
    }
}

struct PositionCoachResult {
    var action: CoachAction
    var confidence: Double
    var message: String
}

enum PositionCoach {
    /// Cut-loss threshold: if the position is down this much or more from
    /// entry, recommend cutting the loss (unless the live signal already
    /// flagged a stop-loss zone).
    private static let cutLossThreshold = -0.03
    /// Take-profit threshold: if the position is up this much or more and
    /// the live signal isn't strongly bullish, recommend locking in gains.
    private static let takeProfitThreshold = 0.05

    static func evaluate(position: Position, signal: DaySignalResponse) -> PositionCoachResult {
        let current = signal.price
        let pnlPct = position.entryPrice != 0 ? (current - position.entryPrice) / position.entryPrice : 0

        if signal.alert == .stopLoss || pnlPct <= cutLossThreshold {
            return PositionCoachResult(
                action: .cutLoss,
                confidence: signal.confidence,
                message: "Down \(percentString(pnlPct)) from your entry. Consider cutting the loss here to protect the rest of your capital."
            )
        }

        if signal.alert == .eodExit {
            return PositionCoachResult(
                action: .takeProfit,
                confidence: signal.confidence,
                message: "The market is closing soon - close same-day positions before the bell rather than holding overnight."
            )
        }

        if signal.alert == .takeProfit || signal.action == .daySell || pnlPct >= takeProfitThreshold {
            return PositionCoachResult(
                action: .takeProfit,
                confidence: signal.confidence,
                message: "Up \(percentString(pnlPct)) and momentum looks like it may be fading - consider locking in some profit."
            )
        }

        return PositionCoachResult(
            action: .hold,
            confidence: signal.confidence,
            message: "No strong exit signal yet. Current P/L: \(percentString(pnlPct)). Keep watching for a take-profit or stop-loss alert."
        )
    }

    private static func percentString(_ pct: Double) -> String {
        let formatted = abs(pct).formatted(.percent.precision(.fractionLength(1)))
        return pct >= 0 ? "+\(formatted)" : "-\(formatted)"
    }
}
