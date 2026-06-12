import SwiftUI

/// "Today" tab - the morning watchlist: current market session plus
/// same-day Buy at Open / Watch for Dip / Avoid candidates with suspected
/// profit targets and a plain-language plan for each.
struct TodayView: View {
    @State private var viewModel = TodayViewModel()

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("Today")
                .luxuryBackground()
                .toolbar {
                    ToolbarItem(placement: .primaryAction) {
                        Button {
                            Task { await viewModel.refresh() }
                        } label: {
                            Label("Refresh", systemImage: "arrow.clockwise")
                        }
                        .disabled(viewModel.isLoading)
                    }
                }
                .task {
                    if viewModel.scan == nil {
                        await viewModel.refresh()
                    }
                }
        }
    }

    @ViewBuilder
    private var content: some View {
        if viewModel.isLoading && viewModel.scan == nil {
            ProgressView("Scanning the morning market...")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = viewModel.errorMessage, viewModel.scan == nil {
            ContentUnavailableView("Couldn't load today's scan", systemImage: "exclamationmark.triangle", description: Text(error))
        } else if let scan = viewModel.scan {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    MarketSessionBanner(session: scan.session)

                    candidateSection(
                        eyebrow: "TOP PICKS",
                        title: "Buy at Open",
                        items: scan.buyAtOpen,
                        emptyText: "No strong buy-at-open candidates right now."
                    )
                    candidateSection(
                        eyebrow: "WATCHLIST",
                        title: "Watch for a Dip",
                        items: scan.watch,
                        emptyText: "Nothing to watch right now."
                    )
                    candidateSection(
                        eyebrow: "CAUTION",
                        title: "Avoid Today",
                        items: scan.avoid,
                        emptyText: "Nothing flagged to avoid right now."
                    )

                    Text(scan.disclaimer)
                        .font(.caption2)
                        .foregroundStyle(Theme.textSecondary)
                        .padding(.top, 4)
                }
                .padding()
            }
            .navigationDestination(for: String.self) { symbol in
                StockDetailView(symbol: symbol)
            }
        }
    }

    private func candidateSection(eyebrow: String, title: String, items: [MorningCandidate], emptyText: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(eyebrow)
                .luxuryEyebrow()
            Text(title)
                .font(Theme.sectionTitleFont())
                .foregroundStyle(Theme.textPrimary)

            if items.isEmpty {
                Text(emptyText)
                    .font(.subheadline)
                    .foregroundStyle(Theme.textSecondary)
            } else {
                VStack(spacing: 10) {
                    ForEach(items) { item in
                        NavigationLink(value: item.symbol) {
                            MorningCandidateCard(candidate: item)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }
}

private struct MorningCandidateCard: View {
    let candidate: MorningCandidate

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(candidate.symbol)
                        .font(Theme.priceFont(18))
                        .foregroundStyle(Theme.textPrimary)
                    Text(candidate.price, format: .currency(code: "USD"))
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(Theme.textSecondary)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    MorningActionBadge(action: candidate.action)
                    if let gap = candidate.gapPercent {
                        Text("\(gap >= 0 ? "+" : "")\(gap, specifier: "%.2f")% gap")
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(gap >= 0 ? Theme.profit : Theme.loss)
                    }
                }
            }

            Text(candidate.plan)
                .font(.subheadline)
                .foregroundStyle(Theme.textPrimary)

            HStack(spacing: 20) {
                statPair("Daily Trend", candidate.dailyTrend.label)
                statPair(
                    "Suspected Profit",
                    "\(String(format: "%.1f", candidate.suspectedProfitPct))% (~\(candidate.suspectedProfitAmount.formatted(.currency(code: "USD"))))"
                )
            }

            if let reason = candidate.reasons.first {
                Text(reason)
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
            }
        }
        .luxuryCard()
    }

    private func statPair(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
            Text(value)
                .font(.caption.monospacedDigit())
                .foregroundStyle(Theme.textPrimary)
        }
    }
}

#Preview {
    TodayView()
        .environmentObject(APIConfig.shared)
}
