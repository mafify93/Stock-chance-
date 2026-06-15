import Foundation

/// Loads the personalized "Daily AI Briefing" for the Today tab - a short
/// AI-generated summary of the user's holdings and watchlist, generated on
/// demand from live data (see `app.daily_briefing` on the backend).
@MainActor
final class DailyBriefingViewModel: ObservableObject {
    @Published private(set) var briefing: DailyBriefingResponse?
    @Published private(set) var isAvailable: Bool?
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    func checkAvailability(baseURL: URL) async {
        let client = APIClient(baseURL: baseURL)
        do {
            let status = try await client.dailyBriefingStatus()
            isAvailable = status.configured
        } catch {
            isAvailable = nil
        }
    }

    func load(baseURL: URL, positions: [Position], watchlist: [String]) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        let request = DailyBriefingRequest(
            positions: positions.map { ChatPosition(symbol: $0.symbol, quantity: $0.quantity, avgEntryPrice: $0.entryPrice) },
            watchlist: watchlist
        )

        let client = APIClient(baseURL: baseURL)
        do {
            briefing = try await client.dailyBriefing(request)
        } catch {
            errorMessage = AutoTraderViewModel.friendlyMessage(for: error)
        }
    }
}
