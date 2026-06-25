import Foundation

/// Drives the pair detail screen: live quote, the swing signal, the same-day
/// intraday signal, and intraday candles for the chart.
@MainActor
final class PairDetailViewModel: ObservableObject {
    let pair: PairInfo

    @Published private(set) var quote: PairQuote?
    @Published private(set) var signal: SignalResponse?
    @Published private(set) var daySignal: DaySignalResponse?
    @Published private(set) var candles: [Candle] = []
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    init(pair: PairInfo) {
        self.pair = pair
    }

    func refresh() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        guard let creds = BrokerStore.shared.dataCredentials else {
            errorMessage = "Add your OANDA API token and account ID in Settings to load this pair."
            return
        }

        let client = APIClient(baseURL: APIConfig.shared.baseURL)
        async let quoteResult = client.quote(pair.pair, creds: creds)
        async let signalResult = client.signal(pair.pair, creds: creds)
        async let dayResult = client.daySignal(pair.pair, creds: creds)
        async let candleResult = client.intradayCandles(pair.pair, granularity: "M5", count: 200, creds: creds)

        // Each piece is best-effort: a failure in one (e.g. not enough
        // intraday data yet) shouldn't blank the whole screen.
        quote = try? await quoteResult
        do {
            signal = try await signalResult
        } catch {
            if !isCancellation(error) { errorMessage = error.localizedDescription }
        }
        daySignal = try? await dayResult
        candles = (try? await candleResult) ?? []
    }
}
