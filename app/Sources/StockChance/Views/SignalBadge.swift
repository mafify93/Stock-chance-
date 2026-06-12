import SwiftUI

extension TradeAction {
    var color: Color {
        switch self {
        case .strongBuy: return .green
        case .buy: return Color(red: 0.4, green: 0.75, blue: 0.4)
        case .hold: return .gray
        case .sell: return Color(red: 0.95, green: 0.55, blue: 0.3)
        case .strongSell: return .red
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
                    .foregroundStyle(.secondary)
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
