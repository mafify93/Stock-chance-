import SwiftUI

struct TodayView: View {
    @StateObject private var viewModel = TodayViewModel()
    @EnvironmentObject private var brokerStore: BrokerStore

    var body: some View {
        NavigationStack {
            ScreenBackground {
                ScrollView {
                    VStack(spacing: 16) {
                        if let session = viewModel.session {
                            SessionBanner(session: session)
                        }

                        if let error = viewModel.errorMessage, viewModel.picks.isEmpty {
                            InfoState(
                                icon: "exclamationmark.triangle.fill",
                                title: "Couldn't load ideas",
                                message: error
                            )
                        }

                        if viewModel.isLoading && viewModel.picks.isEmpty {
                            ProgressView()
                                .tint(Theme.accent)
                                .padding(.top, 40)
                        }

                        if let top = viewModel.picks.first {
                            TopPickHeroCard(pick: top)
                        }

                        if viewModel.picks.count > 1 {
                            VStack(alignment: .leading, spacing: 10) {
                                Text("More Ideas")
                                    .font(Theme.sectionTitleFont())
                                    .foregroundStyle(Theme.textPrimary)
                                    .frame(maxWidth: .infinity, alignment: .leading)

                                ForEach(viewModel.picks.dropFirst()) { pick in
                                    OpportunityRow(pick: pick)
                                }
                            }
                        }

                        DisclaimerText()
                    }
                    .padding()
                }
            }
            .navigationTitle("Forex Chance")
            .navigationDestination(for: String.self) { pairCode in
                PairDetailView(pair: PairInfo.from(code: pairCode))
            }
            .refreshable { await viewModel.refresh() }
        }
        .task { await viewModel.refresh() }
    }
}

private struct TopPickHeroCard: View {
    let pick: Opportunity

    var body: some View {
        NavigationLink(value: pick.pair) {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Text("TOP PICK")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(Theme.accentBright)
                    Spacer()
                    SignalBadge(action: pick.tradeAction)
                }

                Text(pick.display)
                    .font(.system(size: 34, weight: .bold, design: .rounded))
                    .foregroundStyle(Theme.textPrimary)

                Text(pick.headline)
                    .font(.system(.headline, design: .rounded))
                    .foregroundStyle(Theme.textPrimary)

                Text(pick.summary)
                    .font(.subheadline)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                Divider().overlay(Theme.cardBorder)

                HStack {
                    StatTile(label: "Price", value: Format.price(pick.price))
                    StatTile(label: "Target", value: Format.pips(pick.targetPips), valueColor: Theme.profit)
                    StatTile(label: "Stop", value: Format.pips(pick.stopPips.map { -$0 }), valueColor: Theme.loss)
                    StatTile(label: "Confidence", value: "\(Int(pick.confidence))%")
                }
            }
            .heroCardStyle(tint: Theme.color(for: pick.tradeAction))
        }
        .buttonStyle(.plain)
    }
}

private struct OpportunityRow: View {
    let pick: Opportunity

    var body: some View {
        NavigationLink(value: pick.pair) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(pick.display)
                        .font(.system(.headline, design: .rounded))
                        .foregroundStyle(Theme.textPrimary)
                    Text(pick.headline)
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                        .lineLimit(1)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 4) {
                    SignalBadge(action: pick.tradeAction, compact: true)
                    Text("\(Int(pick.confidence))%")
                        .font(.caption2)
                        .foregroundStyle(Theme.textSecondary)
                }
            }
            .cardStyle()
        }
        .buttonStyle(.plain)
    }
}

struct DisclaimerText: View {
    var body: some View {
        Text("Educational technical analysis, not financial advice. Leveraged forex trading carries a high risk of losing money rapidly.")
            .font(.caption2)
            .foregroundStyle(Theme.textSecondary.opacity(0.8))
            .multilineTextAlignment(.center)
            .padding(.top, 8)
    }
}

extension PairInfo {
    /// Build a minimal PairInfo from just an OANDA code (e.g. "EUR_USD"),
    /// used when navigating from a screen that only carries the code.
    static func from(code: String) -> PairInfo {
        let parts = code.split(separator: "_")
        let base = parts.first.map(String.init) ?? code
        let quote = parts.count > 1 ? String(parts[1]) : ""
        let isJPY = quote == "JPY"
        return PairInfo(
            pair: code,
            display: code.replacingOccurrences(of: "_", with: "/"),
            base: base,
            quote: quote,
            pipSize: isJPY ? 0.01 : 0.0001,
            category: "major"
        )
    }
}
