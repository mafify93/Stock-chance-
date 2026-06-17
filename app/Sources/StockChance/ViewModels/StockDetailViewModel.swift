import Foundation

final class StockDetailViewModel: ObservableObject {
    let symbol: String

    @Published private(set) var quote: Quote?
    @Published private(set) var signal: SignalResponse?
    @Published private(set) var candles: [Candle] = []
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    @Published private(set) var daySignal: DaySignalResponse?
    @Published private(set) var intradayCandles: [Candle] = []
    @Published private(set) var dayErrorMessage: String?

    @Published private(set) var aiAnalysis: AIAnalysisResponse?

    private let stream = WatchStreamService()
    private let dayStream = WatchStreamService()
    private var streamTask: Task<Void, Never>?
    private var dayStreamTask: Task<Void, Never>?

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

        await loadDayTrade()
        await loadAIAnalysis()
    }

    /// Loads the combined ML + LLM AI analysis. Best-effort - if it fails
    /// (e.g. no trained model or no `ANTHROPIC_API_KEY`), the rest of the
    /// screen still works and this section is simply hidden.
    @MainActor
    func loadAIAnalysis() async {
        let client = APIClient(baseURL: APIConfig.shared.baseURL)
        do {
            aiAnalysis = try await client.aiAnalysis(symbol)
        } catch {
            aiAnalysis = nil
        }
    }

    /// Loads the same-day signal + intraday candles. Failures here (e.g.
    /// market closed with no data yet) are non-fatal - the daily view above
    /// still works.
    @MainActor
    func loadDayTrade() async {
        dayErrorMessage = nil
        let client = APIClient(baseURL: APIConfig.shared.baseURL)
        do {
            async let dayResult = client.daySignal(symbol)
            async let intradayResult = client.intradayHistory(symbol)
            daySignal = try await dayResult
            intradayCandles = try await intradayResult
        } catch {
            daySignal = nil
            dayErrorMessage = error.localizedDescription
        }
    }

    @MainActor
    func startLive(baseURL: URL) {
        streamTask?.cancel()
        streamTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                do {
                    let updates: AsyncThrowingStream<LiveUpdate, Error> = self.stream.updates(path: "/ws/watch", symbols: [self.symbol], baseURL: baseURL)
                    for try await update in updates {
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

        dayStreamTask?.cancel()
        dayStreamTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                do {
                    let updates: AsyncThrowingStream<DayLiveUpdate, Error> = self.dayStream.updates(path: "/ws/daytrade", symbols: [self.symbol], baseURL: baseURL)
                    for try await update in updates {
                        await MainActor.run {
                            if let signal = update.signal {
                                self.daySignal = signal
                                self.dayErrorMessage = nil
                            } else if let error = update.error {
                                self.dayErrorMessage = error
                            }
                        }
                    }
                } catch {
                    // ignore and retry
                }
                try? await Task.sleep(for: .seconds(10))
            }
        }
    }

    func stopLive() {
        streamTask?.cancel()
        dayStreamTask?.cancel()
        stream.stop()
        dayStream.stop()
    }
}
