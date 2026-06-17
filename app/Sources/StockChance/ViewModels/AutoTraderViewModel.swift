import Foundation

/// Loads and updates the AI Auto-Trader configuration/status from the
/// backend. The backend is the source of truth - this view model just
/// reflects it and lets Settings push changes.
@MainActor
final class AutoTraderViewModel: ObservableObject {
    @Published private(set) var status: AutoTraderStatus?
    @Published private(set) var positions: [AutoTraderPosition] = []
    @Published private(set) var isLoading = false
    @Published private(set) var isSaving = false
    @Published private(set) var isRunning = false
    @Published private(set) var isSelling = false
    @Published private(set) var errorMessage: String?
    @Published var sellMessage: String?

    func load(baseURL: URL) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        let client = APIClient(baseURL: baseURL)
        do {
            status = try await client.autoTraderStatus()
        } catch {
            errorMessage = Self.friendlyMessage(for: error)
        }
        await loadPositions(baseURL: baseURL)
    }

    func loadPositions(baseURL: URL) async {
        let client = APIClient(baseURL: baseURL)
        do {
            positions = try await client.autoTraderPositions()
        } catch {
            // Non-fatal: holdings panel stays empty if fetch fails
        }
    }

    func sellAll(baseURL: URL) async {
        isSelling = true
        sellMessage = nil
        defer { isSelling = false }
        let client = APIClient(baseURL: baseURL)
        do {
            let result = try await client.sellAllPositions()
            sellMessage = result.message.hasPrefix("Sold") ? "✅ \(result.message)" : "⚠️ \(result.message)"
            positions = []
            await load(baseURL: baseURL)
        } catch {
            sellMessage = "❌ \(Self.friendlyMessage(for: error))"
        }
    }

    /// Turns raw API errors into something readable. A 404 here almost always
    /// means the connected backend is an older build without the AI
    /// auto-trader endpoints, so we say so explicitly.
    static func friendlyMessage(for error: Error) -> String {
        let raw = error.localizedDescription
        if raw.localizedCaseInsensitiveContains("not found") || raw.contains("404") {
            return "This backend doesn't have the AI Auto-Trader yet. Update the backend to the latest version and restart it, then try again."
        }
        return raw
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
            return Self.friendlyMessage(for: error)
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
            errorMessage = Self.friendlyMessage(for: error)
        }
    }
}
