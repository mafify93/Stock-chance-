import SwiftUI

/// Trade journal: every broker order placed through Stock Chance, plus
/// manually-logged "Sold" exits from tracked positions, with running win
/// rate and total realized P/L.
struct JournalView: View {
    @EnvironmentObject private var apiConfig: APIConfig
    @StateObject private var store = JournalStore.shared
    @StateObject private var analyticsVM = AnalyticsViewModel()

    var body: some View {
        List {
            Section {
                summaryCard
                    .listRowBackground(Color.clear)
                    .listRowSeparator(.hidden)
                    .listRowInsets(EdgeInsets(top: 6, leading: 16, bottom: 6, trailing: 16))
            }

            Section {
                autoTraderPerformanceCard
                    .listRowBackground(Color.clear)
                    .listRowSeparator(.hidden)
                    .listRowInsets(EdgeInsets(top: 6, leading: 16, bottom: 6, trailing: 16))
            }

            if store.entries.isEmpty {
                EmptyStateView(
                    "No trades logged yet",
                    systemImage: "book.closed",
                    description: Text("Orders placed through Stock Chance, and exits you log from My Positions, will show up here.")
                )
                .listRowBackground(Color.clear)
            } else {
                Section("History") {
                    ForEach(store.entries) { entry in
                        JournalEntryRow(entry: entry)
                            .listRowBackground(Color.clear)
                            .listRowSeparator(.hidden)
                            .listRowInsets(EdgeInsets(top: 4, leading: 16, bottom: 4, trailing: 16))
                    }
                    .onDelete { offsets in
                        for index in offsets {
                            store.remove(store.entries[index])
                        }
                    }
                }
            }
        }
        .listStyle(.plain)
        .luxuryBackground()
        .navigationTitle("Trade Journal")
        .task {
            await analyticsVM.load(baseURL: apiConfig.baseURL)
        }
    }

    private var summaryCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("PERFORMANCE")
                .luxuryEyebrow()
            HStack(spacing: 20) {
                statPair("Total Realized P/L", plText)
                statPair("Win Rate", winRateText)
                statPair("Closed Trades", "\(store.closedTrades.count)")
            }
            Text("Realized P/L only reflects exits you log from My Positions with an exit price. Broker order placements are logged for history but don't include profit/loss unless you log the exit.")
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
        }
        .luxuryCard()
    }

    @ViewBuilder
    private var autoTraderPerformanceCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("AUTO-TRADER HISTORY")
                .luxuryEyebrow()
            if analyticsVM.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, alignment: .center)
            } else if let a = analyticsVM.analytics, a.totalTrades > 0 {
                HStack(spacing: 16) {
                    autoStatPair("Trades", "\(a.totalTrades)")
                    autoStatPair("Win Rate", a.winRate > 0 ? "\(Int(a.winRate))%" : "—")
                    autoStatPair("Total P&L", pnlText(a.totalPnl))
                }
                HStack(spacing: 16) {
                    autoStatPair("Avg Win", pnlText(a.avgWin))
                    autoStatPair("Avg Loss", pnlText(a.avgLoss))
                    autoStatPair("Period", "\(a.periodDays)d")
                }
            } else {
                Text("No auto-trader history yet")
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .luxuryCard()
    }

    private func pnlText(_ value: Double) -> String {
        let formatted = abs(value).formatted(.currency(code: "USD"))
        return value >= 0 ? "+\(formatted)" : "-\(formatted)"
    }

    private func autoStatPair(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
            Text(value)
                .font(.subheadline.weight(.semibold).monospacedDigit())
                .foregroundStyle(Theme.textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var plText: String {
        let total = store.totalRealizedPL
        let formatted = abs(total).formatted(.currency(code: "USD"))
        return total >= 0 ? "+\(formatted)" : "-\(formatted)"
    }

    private var winRateText: String {
        guard let rate = store.winRate else { return "—" }
        return "\(Int(rate))%"
    }

    private func statPair(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
            Text(value)
                .font(.subheadline.weight(.semibold).monospacedDigit())
                .foregroundStyle(plColor(for: title))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func plColor(for title: String) -> Color {
        guard title == "Total Realized P/L" else { return Theme.textPrimary }
        return store.totalRealizedPL >= 0 ? Theme.profit : Theme.loss
    }
}

private struct JournalEntryRow: View {
    let entry: JournalEntry

    private var sideLabel: String { entry.side == "buy" ? "Buy" : "Sell" }
    private var sideColor: Color { entry.side == "buy" ? Theme.profit : Theme.loss }

    private var sourceLabel: String {
        switch entry.source {
        case "paper": return "Alpaca Paper"
        case "live-alpaca": return "Alpaca Live"
        case "questrade": return "Questrade"
        default: return "Manual"
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(entry.symbol)
                        .font(Theme.priceFont(18))
                        .foregroundStyle(Theme.textPrimary)
                    Text(sideLabel)
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(sideColor.opacity(0.18))
                        .foregroundStyle(sideColor)
                        .clipShape(Capsule())
                }
                Text("\(entry.quantity.formatted()) sh @ \(entry.price.formatted(.currency(code: "USD")))")
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                Text("\(sourceLabel) • \(entry.timestamp.formatted(date: .abbreviated, time: .shortened))")
                    .font(.caption2)
                    .foregroundStyle(Theme.textSecondary)
            }

            Spacer()

            if let pl = entry.realizedPL {
                Text("\(pl >= 0 ? "+" : "")\(pl.formatted(.currency(code: "USD")))")
                    .font(.subheadline.weight(.semibold).monospacedDigit())
                    .foregroundStyle(pl >= 0 ? Theme.profit : Theme.loss)
            }
        }
        .padding(.vertical, 6)
        .luxuryCard()
    }
}
