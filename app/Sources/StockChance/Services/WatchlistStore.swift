import Foundation

/// Persists the user's watchlist (list of ticker symbols) to UserDefaults.
final class WatchlistStore: ObservableObject {
    static let shared = WatchlistStore()

    private static let storageKey = "stockchance.watchlist.symbols"
    private static let defaultSymbols = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"]

    @Published var symbols: [String] {
        didSet {
            UserDefaults.standard.set(symbols, forKey: Self.storageKey)
        }
    }

    private init() {
        if let saved = UserDefaults.standard.array(forKey: Self.storageKey) as? [String] {
            self.symbols = saved
        } else {
            self.symbols = Self.defaultSymbols
        }
    }

    func add(_ symbol: String) {
        let upper = symbol.uppercased()
        guard !symbols.contains(upper) else { return }
        symbols.append(upper)
    }

    func remove(_ symbol: String) {
        symbols.removeAll { $0 == symbol.uppercased() }
    }

    func contains(_ symbol: String) -> Bool {
        symbols.contains(symbol.uppercased())
    }

    func toggle(_ symbol: String) {
        if contains(symbol) {
            remove(symbol)
        } else {
            add(symbol)
        }
    }
}
