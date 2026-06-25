import SwiftUI

// MARK: - Signal badge

/// A pill showing a BUY / HOLD / SELL action in its action color.
struct SignalBadge: View {
    let action: TradeAction
    var compact: Bool = false

    var body: some View {
        Text(compact ? action.shortLabel : action.label)
            .font(.system(.caption, design: .rounded).weight(.bold))
            .foregroundStyle(.white)
            .padding(.horizontal, compact ? 8 : 12)
            .padding(.vertical, compact ? 4 : 6)
            .background(
                Capsule().fill(Theme.color(for: action))
            )
    }
}

struct DayActionBadge: View {
    let action: DayAction

    private var color: Color {
        switch action {
        case .buy: return Theme.profit
        case .sell: return Theme.loss
        case .hold: return Theme.neutral
        }
    }

    var body: some View {
        Text(action.label.uppercased())
            .font(.system(.caption, design: .rounded).weight(.bold))
            .foregroundStyle(.white)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Capsule().fill(color))
    }
}

// MARK: - Session banner

/// A compact banner showing the forex trading clock: open/closed, which
/// regional sessions are live, and whether the high-liquidity overlap is on.
struct SessionBanner: View {
    let session: MarketSession

    private var icon: String { session.isOpen ? "globe" : "moon.zzz.fill" }

    private var statusColor: Color {
        if !session.isOpen { return Theme.neutral }
        return session.isHighLiquidity ? Theme.accentBright : Theme.profit
    }

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(statusColor)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(session.isOpen ? "Market Open" : "Market Closed")
                        .font(.system(.subheadline, design: .rounded).weight(.semibold))
                        .foregroundStyle(Theme.textPrimary)
                    if session.isHighLiquidity {
                        Text("PEAK")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(.black)
                            .padding(.horizontal, 5).padding(.vertical, 2)
                            .background(Capsule().fill(Theme.accentBright))
                    }
                }
                Text(session.note)
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer()
        }
        .cardStyle()
    }
}

// MARK: - Stat tile

struct StatTile: View {
    let label: String
    let value: String
    var valueColor: Color = Theme.textPrimary

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(Theme.textSecondary)
            Text(value)
                .font(.system(.callout, design: .rounded).weight(.semibold))
                .foregroundStyle(valueColor)
                .monospacedDigit()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Empty / error states

struct InfoState: View {
    let icon: String
    let title: String
    let message: String

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 40))
                .foregroundStyle(Theme.accent)
            Text(title)
                .font(.system(.headline, design: .rounded))
                .foregroundStyle(Theme.textPrimary)
            Text(message)
                .font(.subheadline)
                .foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
        .padding(.horizontal, 24)
    }
}

// MARK: - Formatting helpers

enum Format {
    static func pips(_ value: Double?) -> String {
        guard let value else { return "—" }
        return String(format: "%+.1f pips", value)
    }

    static func price(_ value: Double?, decimals: Int = 5) -> String {
        guard let value else { return "—" }
        return String(format: "%.\(decimals)f", value)
    }

    static func signedMoney(_ value: Double?, currency: String? = nil) -> String {
        guard let value else { return "—" }
        let suffix = currency.map { " \($0)" } ?? ""
        return String(format: "%+.2f%@", value, suffix)
    }

    static func money(_ value: Double?, currency: String? = nil) -> String {
        guard let value else { return "—" }
        let suffix = currency.map { " \($0)" } ?? ""
        return String(format: "%.2f%@", value, suffix)
    }
}
