import Foundation

/// Drives the "Today" tab: a single ranked "Top Pick" recommendation, the
/// current US market session, and the morning scan of same-day buy/watch/avoid
/// candidates.
final class TodayViewModel: ObservableObject {
    @Published private(set) var session: MarketSession?
    @Published private(set) var topPicks: [Opportunity] = []
    @Published private(set) var scan: MorningScanResponse?
    @Published private(set) var movers: [MoverCandidate] = []
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    @MainActor
    func refresh() async {
        isLoading = true
        errorMessage = nil
        let client = APIClient(baseURL: APIConfig.shared.baseURL)
        do {
            async let sessionResult = client.marketSession()
            async let scanResult = client.morningScan(top: 10)
            async let topPickResult = client.topPick(count: 3)
            async let moversResult = client.movers(top: 6)
            session = try await sessionResult
            scan = try await scanResult
            topPicks = try await topPickResult.picks
            movers = try await moversResult.movers
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
