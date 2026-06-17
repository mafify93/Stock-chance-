import Foundation

@MainActor
final class AnalyticsViewModel: ObservableObject {
    @Published private(set) var analytics: AnalyticsResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    func load(baseURL: URL) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            analytics = try await APIClient(baseURL: baseURL).autoTraderAnalytics()
        } catch {
            errorMessage = AutoTraderViewModel.friendlyMessage(for: error)
        }
    }
}
