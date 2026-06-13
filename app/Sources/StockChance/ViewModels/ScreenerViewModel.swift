import Foundation

/// Drives the "What to buy / what to sell" screener screen.
final class ScreenerViewModel: ObservableObject {
    @Published private(set) var response: ScreenerResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    /// When true, scans the user's watchlist instead of the default universe.
    @Published var useWatchlist = false

    @MainActor
    func refresh(watchlistSymbols: [String]) async {
        isLoading = true
        errorMessage = nil
        let client = APIClient(baseURL: APIConfig.shared.baseURL)
        do {
            let symbols = useWatchlist && !watchlistSymbols.isEmpty ? watchlistSymbols : nil
            response = try await client.screener(symbols: symbols, top: 15)
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
