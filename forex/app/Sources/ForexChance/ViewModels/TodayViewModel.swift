import Foundation

/// Drives the "Today" tab: the forex trading clock plus a ranked set of
/// "Top Pick" trade ideas across the most liquid pairs.
@MainActor
final class TodayViewModel: ObservableObject {
    @Published private(set) var session: MarketSession?
    @Published private(set) var picks: [Opportunity] = []
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    func refresh() async {
        isLoading = true
        errorMessage = nil
        let client = APIClient(baseURL: APIConfig.shared.baseURL)

        // The session clock needs no credentials and should always load.
        do {
            session = try await client.marketSession()
        } catch {
            errorMessage = error.localizedDescription
        }

        guard let creds = BrokerStore.shared.dataCredentials else {
            errorMessage = "Add your OANDA API token and account ID in Settings to load trade ideas."
            isLoading = false
            return
        }

        do {
            picks = try await client.topPick(count: 5, creds: creds).picks
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
