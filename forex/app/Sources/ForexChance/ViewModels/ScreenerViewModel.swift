import Foundation

/// Drives the "Screener" tab: scans the pair universe into Buy / Sell / Hold
/// buckets.
@MainActor
final class ScreenerViewModel: ObservableObject {
    @Published private(set) var response: ScreenerResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    func refresh() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        guard let creds = BrokerStore.shared.dataCredentials else {
            errorMessage = "Add your OANDA API token and account ID in Settings to run the screener."
            return
        }

        let client = APIClient(baseURL: APIConfig.shared.baseURL)
        do {
            response = try await client.screener(top: 12, creds: creds)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
