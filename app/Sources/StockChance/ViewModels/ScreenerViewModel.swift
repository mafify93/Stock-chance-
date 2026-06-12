import Foundation
import Observation

/// Drives the "What to buy / what to sell" screener screen.
@Observable
final class ScreenerViewModel {
    private(set) var response: ScreenerResponse?
    private(set) var isLoading = false
    private(set) var errorMessage: String?

    /// When true, scans the user's watchlist instead of the default universe.
    var useWatchlist = false

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
