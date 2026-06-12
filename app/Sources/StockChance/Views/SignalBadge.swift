import SwiftUI

extension TradeAction {
    var color: Color {
        switch self {
        case .strongBuy, .buy: return Theme.profit
        case .hold: return Theme.gold
        case .sell, .strongSell: return Theme.loss
        }
    }

    var systemImage: String {
        switch self {
        case .strongBuy, .buy: return "arrow.up.circle.fill"
        case .hold: return "minus.circle.fill"
        case .sell, .strongSell: return "arrow.down.circle.fill"
        }
    }
}

/// Compact colored pill showing a Buy/Sell/Hold action.
struct SignalBadge: View {
    let action: TradeAction
    var confidence: Double? = nil

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: action.systemImage)
            Text(action.label)
                .fontWeight(.semibold)
            if let confidence {
                Text("\(Int(confidence))%")
                    .opacity(0.7)
            }
        }
        .font(.caption)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(action.color.opacity(0.18))
        .foregroundStyle(action.color)
        .clipShape(Capsule())
    }
}

/// Compact colored pill for the same-day (intraday) Buy/Sell/Hold action.
struct DayActionBadge: View {
    let action: DayAction
    var confidence: Double? = nil

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: action.systemImage)
            Text(action.label)
                .fontWeight(.semibold)
            if let confidence {
                Text("\(Int(confidence))%")
                    .opacity(0.7)
            }
        }
        .font(.caption)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(action.color.opacity(0.18))
        .foregroundStyle(action.color)
        .clipShape(Capsule())
    }
}

/// Pill for the morning-watchlist action (Buy at Open / Watch / Avoid).
struct MorningActionBadge: View {
    let action: MorningAction

    var body: some View {
        Text(action.label)
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(action.color.opacity(0.18))
            .foregroundStyle(action.color)
            .clipShape(Capsule())
    }
}

/// Small banner for an urgent sell alert ("Take Profit", "Stop Loss", "EOD Exit").
struct AlertBanner: View {
    let alert: DayAlert

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "bell.badge.fill")
            Text(alert.label)
                .font(.subheadline.weight(.semibold))
            Spacer()
        }
        .padding(10)
        .background(alert.color.opacity(0.16))
        .foregroundStyle(alert.color)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(alert.color.opacity(0.4), lineWidth: 1)
        )
    }
}

#Preview {
    VStack(spacing: 12) {
        SignalBadge(action: .strongBuy, confidence: 82)
        SignalBadge(action: .buy, confidence: 61)
        SignalBadge(action: .hold, confidence: 12)
        SignalBadge(action: .sell, confidence: 55)
        SignalBadge(action: .strongSell, confidence: 90)
    }
    .padding()
}
