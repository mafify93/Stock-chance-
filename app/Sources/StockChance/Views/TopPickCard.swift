import SwiftUI

/// The "Today" tab's hero card - one clear, plain-language recommendation
/// combining the longer-term trend, today's intraday momentum, and analyst
/// price targets into a single "what to do right now" idea.
struct TopPickCard: View {
    let opportunity: Opportunity

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("TODAY'S TOP PICK")
                    .luxuryEyebrow()
                Spacer()
                ConfidenceGauge(confidence: opportunity.confidence, tint: opportunity.action.color)
            }

            Text(opportunity.headline)
                .font(.system(.largeTitle, design: .serif).weight(.bold))
                .foregroundStyle(Theme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(opportunity.price, format: .currency(code: "USD"))
                    .font(Theme.priceFont(22))
                    .foregroundStyle(Theme.textPrimary)
                if let change = opportunity.changePercent {
                    Text("\(change >= 0 ? "+" : "")\(change, specifier: "%.2f")%")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(change >= 0 ? Theme.profit : Theme.loss)
                }
            }

            Text(opportunity.summary)
                .font(.subheadline)
                .foregroundStyle(Theme.textSecondary)

            if !opportunity.reasons.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(opportunity.reasons.prefix(3), id: \.self) { reason in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "sparkle")
                                .font(.caption2)
                                .foregroundStyle(opportunity.action.color)
                            Text(reason)
                                .font(.caption)
                                .foregroundStyle(Theme.textPrimary)
                        }
                    }
                }
            }

            if let pct = opportunity.suspectedProfitPct, let amount = opportunity.suspectedProfitAmount {
                Divider().overlay(Theme.cardBorder)
                HStack {
                    Text("Suspected Profit")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(Theme.textPrimary)
                    Spacer()
                    Text("+\(pct, specifier: "%.1f")% (~\(amount.formatted(.currency(code: "USD"))))")
                        .font(.subheadline.monospacedDigit().weight(.semibold))
                        .foregroundStyle(Theme.profit)
                }
            }

            HStack {
                Spacer()
                Label("View Details", systemImage: "arrow.right.circle.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(opportunity.action.color)
            }
        }
        .heroGlassCard(tint: opportunity.action.color)
    }
}

/// Small circular confidence meter shown in the corner of the Top Pick card.
private struct ConfidenceGauge: View {
    let confidence: Double
    let tint: Color

    var body: some View {
        ZStack {
            Circle()
                .stroke(tint.opacity(0.2), lineWidth: 4)
            Circle()
                .trim(from: 0, to: max(0.02, confidence / 100))
                .stroke(tint, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text("\(Int(confidence))%")
                .font(.system(size: 11, weight: .bold, design: .rounded))
                .foregroundStyle(tint)
        }
        .frame(width: 40, height: 40)
    }
}

/// Compact row for the runner-up ideas (#2, #3) below the main Top Pick.
struct RunnerUpRow: View {
    let opportunity: Opportunity

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(opportunity.symbol)
                    .font(Theme.priceFont(16))
                    .foregroundStyle(Theme.textPrimary)
                Text(opportunity.headline)
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(1)
            }
            Spacer()
            SignalBadge(action: opportunity.action, confidence: opportunity.confidence)
        }
        .luxuryCard()
    }
}
