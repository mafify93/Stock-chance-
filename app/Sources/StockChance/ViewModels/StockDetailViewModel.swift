import Foundation
import Observation

@Observable
final class StockDetailViewModel {
    let symbol: String

    private(set) var quote: Quote?
    private(set) var signal: SignalResponse?
    private(set) var candles: [Candle] = []
    private(set) var isLoading = false
    private(set) var errorMessage: String?

    private let stream = WatchStreamService()
    private var streamTask: Task<Void, Never>?

    init(symbol: String) {
        self.symbol = symbol
    }

    @MainActor
    func load() async {
        isLoading = true
        errorMessage = nil
        let client = APIClient(baseURL: APIConfig.shared.baseURL)

        do {
            async let quoteResult = client.quote(symbol)
            async let signalResult = client.signal(symbol)
            async let historyResult = client.history(symbol, period: "6mo", interval: "1d")

            quote = try await quoteResult
            signal = try await signalResult
            candles = try await historyResult
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    @MainActor
    func startLive(baseURL: URL) {
        streamTask?.cancel()
        streamTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                do {
                    for try await update in self.stream.updates(for: [self.symbol], baseURL: baseURL) {
                        await MainActor.run {
                            if let quote = update.quote {
                                self.quote = quote
                            }
                            if let live = update.signal, var signal = self.signal {
                                signal.action = live.action
                                signal.score = live.score
                                signal.confidence = live.confidence
                                signal.reasons = live.reasons
                                signal.levels = live.levels
                                self.signal = signal
                            }
                        }
                    }
                } catch {
                    // ignore and retry
                }
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }

    func stopLive() {
        streamTask?.cancel()
        stream.stop()
    }
}
