import Foundation

/// Persists per-symbol watchlist alerts (price thresholds / signal-change
/// notifications) to UserDefaults, keyed by uppercased symbol.
final class WatchlistAlertStore: ObservableObject {
    static let shared = WatchlistAlertStore()

    private static let storageKey = "stockchance.watchlist.alerts"

    @Published private(set) var alerts: [String: WatchlistAlert] {
        didSet { save() }
    }

    private init() {
        if let data = UserDefaults.standard.data(forKey: Self.storageKey),
           let decoded = try? JSONDecoder().decode([String: WatchlistAlert].self, from: data) {
            self.alerts = decoded
        } else {
            self.alerts = [:]
        }
    }

    private func save() {
        if let data = try? JSONEncoder().encode(alerts) {
            UserDefaults.standard.set(data, forKey: Self.storageKey)
        }
    }

    func alert(for symbol: String) -> WatchlistAlert? {
        alerts[symbol.uppercased()]
    }

    /// Saves the alert, or removes it entirely if it no longer specifies
    /// any condition.
    func set(_ alert: WatchlistAlert) {
        let key = alert.symbol.uppercased()
        if alert.isActive {
            alerts[key] = alert
        } else {
            alerts.removeValue(forKey: key)
        }
    }

    func remove(_ symbol: String) {
        alerts.removeValue(forKey: symbol.uppercased())
    }

    /// Records the most recently observed signal action for a symbol with an
    /// active alert, so the next change can be detected. Persisted, so this
    /// survives app relaunches and background refreshes.
    func updateLastSignalAction(_ action: TradeAction, for symbol: String) {
        let key = symbol.uppercased()
        guard var alert = alerts[key] else { return }
        alert.lastSignalAction = action
        alerts[key] = alert
    }
}
