import Foundation

/// Streams live same-day signals for every symbol the user holds a
/// position in, and triggers a local notification whenever the backend
/// flags an alert (take-profit / stop-loss / end-of-day exit) or a
/// "Sell Now" action.
final class PositionsViewModel: ObservableObject {
    @Published private(set) var liveSignals: [String: DaySignalResponse] = [:]
    @Published private(set) var isConnected = false

    private let stream = WatchStreamService()
    private var streamTask: Task<Void, Never>?
    private var currentSymbols: [String] = []

    @MainActor
    func start(symbols: [String], baseURL: URL) {
        let normalized = Array(Set(symbols.map { $0.uppercased() })).sorted()
        guard normalized != currentSymbols else { return }
        currentSymbols = normalized
        streamTask?.cancel()
        stream.stop()

        guard !normalized.isEmpty else {
            liveSignals = [:]
            isConnected = false
            return
        }

        streamTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                do {
                    let updates: AsyncThrowingStream<DayLiveUpdate, Error> = self.stream.updates(path: "/ws/daytrade", symbols: normalized, baseURL: baseURL)
                    for try await update in updates {
                        await MainActor.run {
                            self.isConnected = true
                            if let signal = update.signal {
                                self.liveSignals[update.symbol] = signal
                                self.notifyIfNeeded(symbol: update.symbol, signal: signal)
                            }
                        }
                    }
                } catch {
                    await MainActor.run { self.isConnected = false }
                }
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }

    @MainActor
    private func notifyIfNeeded(symbol: String, signal: DaySignalResponse) {
        let price = signal.price.formatted(.currency(code: "USD"))
        if let alert = signal.alert {
            NotificationManager.shared.notify(
                key: "\(symbol)-\(alert.rawValue)",
                title: "\(symbol): \(alert.label)",
                body: "Now trading at \(price)."
            )
        } else if signal.action == .daySell {
            NotificationManager.shared.notify(
                key: "\(symbol)-SELL_NOW",
                title: "\(symbol): Sell Now signal",
                body: "The same-day signal flipped to Sell Now at \(price)."
            )
        }
    }

    func stop() {
        streamTask?.cancel()
        stream.stop()
        currentSymbols = []
        isConnected = false
    }
}
