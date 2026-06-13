import Foundation

/// Holds the user's Alpaca paper-trading API credentials in the Keychain.
///
/// Credentials are never written to UserDefaults, never bundled with the
/// app, and never stored by the backend - they're sent with each broker
/// request and forwarded directly to Alpaca's **paper trading** endpoint.
@MainActor
final class BrokerStore: ObservableObject {
    static let shared = BrokerStore()

    private static let keyIdKey = "alpaca.apiKeyId"
    private static let secretKeyKey = "alpaca.apiSecretKey"

    @Published var apiKeyId: String {
        didSet { KeychainStore.set(apiKeyId, for: Self.keyIdKey) }
    }

    @Published var apiSecretKey: String {
        didSet { KeychainStore.set(apiSecretKey, for: Self.secretKeyKey) }
    }

    private init() {
        apiKeyId = KeychainStore.get(Self.keyIdKey) ?? ""
        apiSecretKey = KeychainStore.get(Self.secretKeyKey) ?? ""
    }

    var credentials: BrokerCredentials {
        BrokerCredentials(apiKeyId: apiKeyId, apiSecretKey: apiSecretKey)
    }

    var isConfigured: Bool {
        credentials.isConfigured
    }

    func clear() {
        apiKeyId = ""
        apiSecretKey = ""
    }
}
