import SwiftUI

/// Small banner showing the current US market session (pre-market / open /
/// after-hours / closed) and a rough countdown to the next transition.
struct MarketSessionBanner: View {
    let session: MarketSession

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(session.status.color)
                .frame(width: 10, height: 10)
                .shadow(color: session.status.color.opacity(0.6), radius: 4)

            VStack(alignment: .leading, spacing: 2) {
                Text(session.status.label)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
            }

            Spacer()

            Text(session.nowEt)
                .font(.caption.monospacedDigit())
                .foregroundStyle(Theme.textSecondary)
        }
        .padding(12)
        .background(Theme.backgroundElevated)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(Theme.cardBorder.opacity(0.5), lineWidth: 1)
        )
    }

    private var subtitle: String {
        if let minutes = session.minutesToOpen {
            return "Opens in \(minutes) min"
        } else if let minutes = session.minutesToClose {
            return "Closes in \(minutes) min"
        } else if session.isWeekday {
            return "Markets reopen tomorrow"
        } else {
            return "Markets reopen Monday"
        }
    }
}

#Preview {
    VStack(spacing: 12) {
        MarketSessionBanner(session: MarketSession(status: .open, nowEt: "11:42 AM ET", minutesToClose: 258, minutesToOpen: nil, isWeekday: true))
        MarketSessionBanner(session: MarketSession(status: .preMarket, nowEt: "8:15 AM ET", minutesToClose: nil, minutesToOpen: 75, isWeekday: true))
        MarketSessionBanner(session: MarketSession(status: .closed, nowEt: "10:00 PM ET", minutesToClose: nil, minutesToOpen: nil, isWeekday: false))
    }
    .padding()
    .luxuryBackground()
}
