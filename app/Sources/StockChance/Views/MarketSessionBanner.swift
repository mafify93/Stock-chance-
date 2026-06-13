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

            Text(formattedTime)
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

    /// Formats the backend's ISO-8601 "now in Eastern Time" timestamp as a
    /// short, human-readable clock time (e.g. "1:41 PM ET").
    private var formattedTime: String {
        let isoFormatter = ISO8601DateFormatter()
        isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = isoFormatter.date(from: session.nowEt) else {
            return session.nowEt
        }
        let timeFormatter = DateFormatter()
        timeFormatter.dateFormat = "h:mm a"
        timeFormatter.timeZone = TimeZone(identifier: "America/New_York")
        return timeFormatter.string(from: date) + " ET"
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
