import Foundation

/// Persists the user's trade journal - every broker order placed through
/// Stock Chance, plus manually-tracked buy/sell entries - to UserDefaults.
final class JournalStore: ObservableObject {
    static let shared = JournalStore()

    private static let storageKey = "stockchance.journal"

    @Published var entries: [JournalEntry] {
        didSet { save() }
    }

    private init() {
        if let data = UserDefaults.standard.data(forKey: Self.storageKey),
           let decoded = try? JSONDecoder().decode([JournalEntry].self, from: data) {
            self.entries = decoded
        } else {
            self.entries = []
        }
    }

    private func save() {
        if let data = try? JSONEncoder().encode(entries) {
            UserDefaults.standard.set(data, forKey: Self.storageKey)
        }
    }

    func log(symbol: String, side: String, quantity: Double, price: Double, source: String, realizedPL: Double? = nil) {
        entries.insert(
            JournalEntry(symbol: symbol.uppercased(), side: side, quantity: quantity, price: price, timestamp: Date(), source: source, realizedPL: realizedPL),
            at: 0
        )
    }

    func remove(_ entry: JournalEntry) {
        entries.removeAll { $0.id == entry.id }
    }

    /// Closed (realized) trades only - used for win-rate / total P/L stats.
    var closedTrades: [JournalEntry] {
        entries.filter { $0.realizedPL != nil }
    }

    var totalRealizedPL: Double {
        closedTrades.reduce(0) { $0 + ($1.realizedPL ?? 0) }
    }

    var winRate: Double? {
        let closed = closedTrades
        guard !closed.isEmpty else { return nil }
        let wins = closed.filter { ($0.realizedPL ?? 0) > 0 }.count
        return Double(wins) / Double(closed.count) * 100
    }
}
