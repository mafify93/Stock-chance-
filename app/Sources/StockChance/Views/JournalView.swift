import SwiftUI

/// Trade journal: every broker order placed through Stock Chance, plus
/// manually-logged "Sold" exits from tracked positions, with running win
/// rate and total realized P/L.
struct JournalView: View {
    @StateObject private var store = JournalStore.shared

    var body: some View {
        List {
            Section {
                summaryCard
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
