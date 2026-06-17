import Foundation

/// Loads "Tonight's Picks" - the nightly AI deep-research scan - from the
/// backend. The scan itself runs automatically on the backend every evening;
/// this view model just reflects the latest result and offers a manual
/// "Run Now" for testing.
@MainActor
final class NightScanViewModel: ObservableObject {
    @Published private(set) var status: NightScanStatus?
    @Published private(set) var isLoading = false
    @Published private(set) var isRunning = false
    @Published private(set) var errorMessage: String?

    func load(baseURL: URL) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        let client = APIClient(baseURL: baseURL)
        do {
            status = try await client.nightScanStatus()
        } catch {
            errorMessage = AutoTraderViewModel.friendlyMessage(for: error)
        }
    }

    func runNow(baseURL: URL) async {
        isRunning = true
        errorMessage = nil
        defer { isRunning = false }
        let client = APIClient(baseURL: baseURL)
        do {
            status = try await client.runNightScanNow()
        } catch {
            errorMessage = AutoTraderViewModel.friendlyMessage(for: error)
        }
    }
}
