import Foundation

/// Drives the watchlist screen: keeps a live WebSocket connection open for
/// every symbol the user is watching and republishes quote + signal updates.
final class WatchlistViewModel: ObservableObject {
    @Published private(set) var liveData: [String: LiveUpdate] = [:]
    @Published private(set) var isConnected = false

    private let stream = WatchStreamService()
    private var streamTask: Task<Void, Never>?
    private var currentSymbols: [String] = []

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
        WatchlistAlertChecker.check(
            symbol: update.symbol,
            price: update.quote?.price,
            currency: update.quote?.currency ?? "USD",
            action: update.signal?.action
        )
    }
}
