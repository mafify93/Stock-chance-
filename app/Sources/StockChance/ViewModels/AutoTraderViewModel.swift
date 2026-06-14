import Foundation

/// Loads and updates the AI Auto-Trader configuration/status from the
/// backend. The backend is the source of truth - this view model just
/// reflects it and lets Settings push changes.
@MainActor
final class AutoTraderViewModel: ObservableObject {
    @Published private(set) var status: AutoTraderStatus?
    @Published private(set) var isLoading = false
    @Published private(set) var isSaving = false
    @Published private(set) var isRunning = false
    @Published private(set) var errorMessage: String?

    func load(baseURL: URL) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        let client = APIClient(baseURL: baseURL)
        do {
            status = try await client.autoTraderStatus()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Saves the new configuration and refreshes status. Returns an error
    /// message on failure (e.g. invalid environment), or `nil` on success.
    func save(_ request: AutoTraderConfigRequest, baseURL: URL) async -> String? {
        isSaving = true
        defer { isSaving = false }
        let client = APIClient(baseURL: baseURL)
        do {
            _ = try await client.updateAutoTraderConfig(request)
            await load(baseURL: baseURL)
            return nil
        } catch {
            return error.localizedDescription
        }
    }

    func runNow(baseURL: URL) async {
        isRunning = true
        errorMessage = nil
        defer { isRunning = false }
        let client = APIClient(baseURL: baseURL)
        do {
            status = try await client.runAutoTraderNow()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
