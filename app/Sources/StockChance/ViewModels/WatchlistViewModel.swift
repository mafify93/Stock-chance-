import Foundation
import Observation

/// Drives the watchlist screen: keeps a live WebSocket connection open for
/// every symbol the user is watching and republishes quote + signal updates.
@Observable
final class WatchlistViewModel {
    private(set) var liveData: [String: LiveUpdate] = [:]
    private(set) var isConnected = false

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
}
