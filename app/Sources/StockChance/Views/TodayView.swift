import SwiftUI

/// "Today" tab - the morning watchlist: current market session plus
/// same-day Buy at Open / Watch for Dip / Avoid candidates with suspected
/// profit targets and a plain-language plan for each.
struct TodayView: View {
    @EnvironmentObject private var apiConfig: APIConfig
    @EnvironmentObject private var brokerStore: BrokerStore
    @StateObject private var viewModel = TodayViewModel()
    @StateObject private var nightScanViewModel = NightScanViewModel()
    @State private var showSettings = false

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
                    ToolbarItem(placement: .cancellationAction) {
                        Button {
                            showSettings = true
                        } label: {
                            Label("Settings", systemImage: "gear")
                        }
                    }
                }
                .sheet(isPresented: $showSettings) {
                    SettingsView()
                        .environmentObject(apiConfig)
                        .environmentObject(brokerStore)
                }
                .task {
                    if viewModel.scan == nil {
                        await viewModel.refresh()
                    }
                }
                .task {
                    await nightScanViewModel.load(baseURL: apiConfig.baseURL)
                }
                .task {
                    // Keep the morning scan reasonably fresh while this tab
                    // is visible, without a disruptive full-screen reload.
                    while !Task.isCancelled {
                        try? await Task.sleep(for: .seconds(60))
                        if Task.isCancelled { break }
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
            EmptyStateView("Couldn't load today's scan", systemImage: "exclamationmark.triangle", description: Text(error))
        } else if let scan = viewModel.scan {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    MarketSessionBanner(session: scan.session)

                    tonightsPicksSection

                    if let topPick = viewModel.topPicks.first {
                        NavigationLink(value: topPick.symbol) {
                            TopPickCard(opportunity: topPick)
                        }
                        .buttonStyle(.plain)
                    }

                    if viewModel.topPicks.count > 1 {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("ALSO LOOKING GOOD")
                                .luxuryEyebrow()
                            VStack(spacing: 10) {
                                ForEach(viewModel.topPicks.dropFirst()) { pick in
                                    NavigationLink(value: pick.symbol) {
                                        RunnerUpRow(opportunity: pick)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }

                    if !viewModel.movers.isEmpty {
                        moversSection
                    }

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

    private var moversSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("PRE-MARKET")
                    .luxuryEyebrow()
                InfoTooltip(title: TradingGlossary.momentumScore.0, text: TradingGlossary.momentumScore.1)
            }
            Text("Pre-Market Movers")
                .font(Theme.sectionTitleFont())
                .foregroundStyle(Theme.textPrimary)
            Text("What's unusually active right now - not a prediction of how far a move will go.")
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(viewModel.movers) { mover in
                        NavigationLink(value: mover.symbol) {
                            MoverCard(mover: mover)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var tonightsPicksSection: some View {
        if let status = nightScanViewModel.status, status.configured {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("TONIGHT'S PICKS")
                        .luxuryEyebrow()
                    InfoTooltip(title: TradingGlossary.tonightsPicks.0, text: TradingGlossary.tonightsPicks.1)
                    Spacer()
                    if let result = status.result {
                        Text(result.date, format: .relative(presentation: .named))
                            .font(.caption2)
                            .foregroundStyle(Theme.textSecondary)
                    }
                }
                Text("What to Consider for Tomorrow")
                    .font(Theme.sectionTitleFont())
                    .foregroundStyle(Theme.textPrimary)

                if let result = status.result {
                    ExpandableText(text: result.summary, lineLimit: 2, font: .subheadline, color: Theme.textSecondary)

                    if result.picks.isEmpty {
                        Text("No strong catalysts found in last night's scan.")
                            .font(.subheadline)
                            .foregroundStyle(Theme.textSecondary)
                    } else {
                        VStack(spacing: 10) {
                            ForEach(result.picks) { pick in
                                NavigationLink(value: pick.symbol) {
                                    NightPickCard(pick: pick)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }

                    Text(result.disclaimer)
                        .font(.caption2)
                        .foregroundStyle(Theme.textSecondary.opacity(0.8))
                } else {
                    Text("The AI researches the market automatically every evening (around 8 PM ET) - check back tonight for tomorrow's picks.")
                        .font(.subheadline)
                        .foregroundStyle(Theme.textSecondary)
                }
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

            ExpandableText(text: candidate.plan, lineLimit: 2, font: .subheadline, color: Theme.textPrimary)

            HStack(spacing: 20) {
                statPair("Daily Trend", candidate.dailyTrend.label)
                statPair(
                    "Suspected Profit",
                    "\(String(format: "%.1f", candidate.suspectedProfitPct))% (~\(candidate.suspectedProfitAmount.formatted(.currency(code: "USD"))))"
                )
            }

            if let reason = candidate.reasons.first {
                ExpandableText(text: reason, lineLimit: 1, font: .caption, color: Theme.textSecondary)
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

/// Compact card for a single "Pre-Market Movers" candidate: price, overnight
/// gap, relative volume, and risk flags for extreme/illiquid movers.
private struct MoverCard: View {
    let mover: MoverCandidate

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(mover.symbol)
                .font(Theme.priceFont(18))
                .foregroundStyle(Theme.textPrimary)

            Text(mover.price, format: .currency(code: "USD"))
                .font(.caption.monospacedDigit())
                .foregroundStyle(Theme.textSecondary)

            Text("\(mover.changePercent >= 0 ? "+" : "")\(mover.changePercent, specifier: "%.2f")%")
                .font(.subheadline.weight(.semibold).monospacedDigit())
                .foregroundStyle(mover.changePercent >= 0 ? Theme.profit : Theme.loss)

            if let relVol = mover.relativeVolume {
                Text("\(relVol, specifier: "%.1f")x avg volume")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(Theme.textSecondary)
            }

            if !mover.riskFlags.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(mover.riskFlags, id: \.self) { flag in
                        if let risk = MoverRiskFlag(rawValue: flag) {
                            Text(risk.label)
                                .font(.caption2.weight(.semibold))
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Theme.loss.opacity(0.18))
                                .foregroundStyle(Theme.loss)
                                .clipShape(Capsule())
                        }
                    }
                }
            }
        }
        .padding(12)
        .frame(width: 140, alignment: .leading)
        .background(Theme.card)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(Theme.cardBorder.opacity(0.5), lineWidth: 1)
        )
    }
}

/// Card for a single "Tonight's Picks" recommendation: symbol, BUY/WATCH
/// badge with confidence, the news catalyst found by the AI, and a short
/// plan for the next session.
private struct NightPickCard: View {
    let pick: NightPick

    private var isBuy: Bool { pick.action == "BUY" }
    private var actionColor: Color { isBuy ? Theme.profit : Theme.gold }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 8) {
                Text(pick.symbol)
                    .font(Theme.priceFont(18))
                    .foregroundStyle(Theme.textPrimary)

                Spacer()

                Text(isBuy ? "BUY" : "WATCH")
                    .font(.caption.weight(.bold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(actionColor.opacity(0.18))
                    .foregroundStyle(actionColor)
                    .clipShape(Capsule())

                Text("\(Int(pick.confidence))%")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(Theme.textSecondary)
            }

            ExpandableText(text: pick.catalyst, lineLimit: 2, font: .subheadline, color: Theme.textPrimary)

            ExpandableText(text: pick.plan, lineLimit: 2, font: .caption, color: Theme.textSecondary)
        }
        .luxuryCard()
    }
}
