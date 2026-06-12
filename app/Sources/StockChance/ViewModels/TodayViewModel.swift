import Foundation
import Observation

/// Drives the "Today" tab: the current US market session plus the morning
/// scan of same-day buy/watch/avoid candidates.
@Observable
final class TodayViewModel {
    private(set) var session: MarketSession?
    private(set) var scan: MorningScanResponse?
    private(set) var isLoading = false
    private(set) var errorMessage: String?

    @MainActor
    func refresh() async {
        isLoading = true
        errorMessage = nil
        let client = APIClient(baseURL: APIConfig.shared.baseURL)
        do {
            async let sessionResult = client.marketSession()
            async let scanResult = client.morningScan(top: 10)
            session = try await sessionResult
            scan = try await scanResult
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
