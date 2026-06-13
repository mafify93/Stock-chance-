import Foundation

/// Drives the watchlist screen: keeps a live WebSocket connection open for
/// every symbol the user is watching and republishes quote + signal updates.
final class WatchlistViewModel: ObservableObject {
    @Published private(set) var liveData: [String: LiveUpdate] = [:]
    @Published private(set) var isConnected = false

    private let stream = WatchStreamService()
    private var streamTask: Task<Void, Never>?
    private var currentSymbols: [String] = []
    private var lastSignalAction: [String: TradeAction] = [:]

    @MainActor
    func start(symbols: [String], baseURL: URL) {
        guard symbols != currentSymbols else { return }
        currentSymbols = symbols
        streamTask?.cancel()
        stream.stop()

        guard !symbols.isEmpty else {
            liveData = [:]
            isConnected = false
            return
        }

        streamTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                do {
                    let updates: AsyncThrowingStream<LiveUpdate, Error> = self.stream.updates(path: "/ws/watch", symbols: symbols, baseURL: baseURL)
                    for try await update in updates {
                        await MainActor.run {
                            self.isConnected = true
                            self.liveData[update.symbol] = update
                            self.checkAlerts(for: update)
                        }
                    }
                } catch {
                    await MainActor.run { self.isConnected = false }
                }
                // brief backoff before reconnecting
                try? await Task.sleep(for: .seconds(3))
            }
        }
    }

    func stop() {
        streamTask?.cancel()
        stream.stop()
        currentSymbols = []
        isConnected = false
    }

    /// Fires a local notification if `update` crosses a user-configured
    /// price threshold or its signal action just changed (when the user
    /// asked to be notified about that).
    @MainActor
    private func checkAlerts(for update: LiveUpdate) {
        let symbol = update.symbol
        guard let alert = WatchlistAlertStore.shared.alert(for: symbol), alert.isActive else {
            lastSignalAction[symbol] = update.signal?.action
            return
        }

        if let quote = update.quote {
            let currency = quote.currency ?? "USD"
            if let above = alert.priceAbove, quote.price >= above {
                NotificationManager.shared.notify(
                    key: "watchlist-price-above-\(symbol)",
                    title: "\(symbol) is above \(above.formatted(.currency(code: currency)))",
                    body: "Now trading at \(quote.price.formatted(.currency(code: currency)))."
                )
            }
            if let below = alert.priceBelow, quote.price <= below {
                NotificationManager.shared.notify(
                    key: "watchlist-price-below-\(symbol)",
                    title: "\(symbol) is below \(below.formatted(.currency(code: currency)))",
                    body: "Now trading at \(quote.price.formatted(.currency(code: currency)))."
                )
            }
        }

        if alert.notifyOnSignalChange, let signal = update.signal {
            if let previous = lastSignalAction[symbol], previous != signal.action {
                NotificationManager.shared.notify(
                    key: "watchlist-signal-\(symbol)-\(signal.action.rawValue)",
                    title: "\(symbol) signal changed to \(signal.action.label)",
                    body: "The technical signal for \(symbol) just changed to \(signal.action.label)."
                )
            }
            lastSignalAction[symbol] = signal.action
        }
    }
}
