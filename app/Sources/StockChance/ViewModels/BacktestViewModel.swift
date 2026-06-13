import Foundation

@MainActor
final class BacktestViewModel: ObservableObject {
    @Published private(set) var result: BacktestResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?
    @Published var period: String = "2y" {
        didSet {
            if oldValue != period {
                Task { await load() }
            }
        }
    }

    let symbol: String
    private let baseURL: URL

    init(symbol: String, baseURL: URL) {
        self.symbol = symbol
        self.baseURL = baseURL
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        let client = APIClient(baseURL: baseURL)
        do {
            result = try await client.backtest(symbol, period: period)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
