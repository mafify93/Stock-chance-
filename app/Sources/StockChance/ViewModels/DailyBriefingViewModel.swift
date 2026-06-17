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

    private static let cacheKey = "dailyBriefing.cache"
    private static let cacheDateKey = "dailyBriefing.date"

    func checkAvailability(baseURL: URL) async {
        let client = APIClient(baseURL: baseURL)
        do {
            let status = try await client.dailyBriefingStatus()
            isAvailable = status.configured
        } catch {
            isAvailable = nil
        }
    }

    /// Returns true if we have a cached briefing from today, so the caller
    /// can skip the API call on app relaunch.
    func loadCached() -> Bool {
        let today = Calendar.current.startOfDay(for: Date()).timeIntervalSince1970
        guard
            let raw = UserDefaults.standard.data(forKey: Self.cacheKey),
            let cached = try? APIClient.decoder.decode(DailyBriefingResponse.self, from: raw),
            UserDefaults.standard.double(forKey: Self.cacheDateKey) == today
        else { return false }
        briefing = cached
        return true
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
            let result = try await client.dailyBriefing(request)
            briefing = result
            if let data = try? APIClient.encoder.encode(result) {
                let today = Calendar.current.startOfDay(for: Date()).timeIntervalSince1970
                UserDefaults.standard.set(data, forKey: Self.cacheKey)
                UserDefaults.standard.set(today, forKey: Self.cacheDateKey)
            }
        } catch {
            errorMessage = AutoTraderViewModel.friendlyMessage(for: error)
        }
    }
}
