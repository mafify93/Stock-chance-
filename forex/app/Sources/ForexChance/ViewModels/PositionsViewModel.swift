import Foundation

/// Drives the "Positions" tab: the OANDA account summary and open positions,
/// for the currently-selected environment (practice/live).
@MainActor
final class PositionsViewModel: ObservableObject {
    @Published var environment: OandaEnvironment = .practice
    @Published private(set) var account: BrokerAccount?
    @Published private(set) var positions: [BrokerPosition] = []
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?
    @Published var actionMessage: String?

    func refresh() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        let store = BrokerStore.shared
        // Fall back to whichever environment is actually configured.
        if !store.credentials(for: environment).isConfigured {
            if let first = store.availableEnvironments.first {
                environment = first
            } else {
                errorMessage = "Add your OANDA API token and account ID in Settings to view positions."
                account = nil
                positions = []
                return
            }
        }

        let creds = store.credentials(for: environment)
        let client = APIClient(baseURL: APIConfig.shared.baseURL)

        // Load the two independently: a failure (or cancellation) of one
        // shouldn't blank out the other. The account summary is the more
        // important of the two, so surface its error if it fails.
        do {
            account = try await client.account(creds: creds)
        } catch {
            if !isCancellation(error) { errorMessage = error.localizedDescription }
        }

        do {
            positions = try await client.positions(creds: creds)
        } catch {
            if !isCancellation(error) { errorMessage = error.localizedDescription }
        }
    }

    func close(_ position: BrokerPosition) async {
        let creds = BrokerStore.shared.credentials(for: environment)
        let client = APIClient(baseURL: APIConfig.shared.baseURL)
        do {
            let result = try await client.closePosition(
                CloseRequest(pair: position.pair, side: position.side), creds: creds
            )
            actionMessage = result.message
            await refresh()
        } catch {
            actionMessage = error.localizedDescription
        }
    }
}
