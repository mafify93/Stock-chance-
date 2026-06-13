import Foundation

/// One brokerage account the user can place orders through, surfaced as a
/// single picker option in the order sheet.
enum TradeAccount: Identifiable, Hashable {
    case alpacaPaper
    case alpacaLive
    case questrade(accountNumber: String)

    var id: String {
        switch self {
        case .alpacaPaper: return "alpaca-paper"
        case .alpacaLive: return "alpaca-live"
        case .questrade(let accountNumber): return "questrade-\(accountNumber)"
        }
    }

    var label: String {
        switch self {
        case .alpacaPaper: return "Alpaca Paper (Simulated)"
        case .alpacaLive: return "Alpaca Live (Real Money)"
        case .questrade(let accountNumber): return "Questrade \(accountNumber) (Real Money)"
        }
    }

    /// Whether orders placed against this account use real money.
    var isLive: Bool {
        switch self {
        case .alpacaPaper: return false
        case .alpacaLive, .questrade: return true
        }
    }
}

/// Holds the user's brokerage credentials in the Keychain.
///
/// Credentials are never written to UserDefaults, never bundled with the
/// app, and never stored by the backend - they're sent with each broker
/// request. Paper-trading credentials always work; **live** Alpaca and
/// Questrade credentials are only used once the user has explicitly
/// acknowledged that live trading places real orders with real money
/// (`liveTradingAcknowledged`).
@MainActor
final class BrokerStore: ObservableObject {
    static let shared = BrokerStore()

    private static let keyIdKey = "alpaca.apiKeyId"
    private static let secretKeyKey = "alpaca.apiSecretKey"
    private static let liveAckKey = "broker.liveTradingAcknowledged"
    private static let liveKeyIdKey = "alpaca.live.apiKeyId"
    private static let liveSecretKeyKey = "alpaca.live.apiSecretKey"
    private static let qtRefreshTokenKey = "questrade.refreshToken"
    private static let qtAccessTokenKey = "questrade.accessToken"
    private static let qtApiServerKey = "questrade.apiServer"
    private static let qtAccountNumberKey = "questrade.accountNumber"
    private static let qtExpiryKey = "questrade.accessTokenExpiry"

    // Alpaca paper trading (simulated - no real money)
    @Published var apiKeyId: String {
        didSet { KeychainStore.set(apiKeyId, for: Self.keyIdKey) }
    }

    @Published var apiSecretKey: String {
        didSet { KeychainStore.set(apiSecretKey, for: Self.secretKeyKey) }
    }

    // Explicit "I understand this is real money" acknowledgment, required
    // before any live Alpaca or Questrade credentials are used.
    @Published var liveTradingAcknowledged: Bool {
        didSet { KeychainStore.set(liveTradingAcknowledged ? "1" : "", for: Self.liveAckKey) }
    }

    // Alpaca live trading (REAL money)
    @Published var liveApiKeyId: String {
        didSet { KeychainStore.set(liveApiKeyId, for: Self.liveKeyIdKey) }
    }

    @Published var liveApiSecretKey: String {
        didSet { KeychainStore.set(liveApiSecretKey, for: Self.liveSecretKeyKey) }
    }

    // Questrade live trading (REAL money)
    @Published var questradeRefreshToken: String {
        didSet { KeychainStore.set(questradeRefreshToken, for: Self.qtRefreshTokenKey) }
    }

    @Published var questradeAccessToken: String {
        didSet { KeychainStore.set(questradeAccessToken, for: Self.qtAccessTokenKey) }
    }

    @Published var questradeApiServer: String {
        didSet { KeychainStore.set(questradeApiServer, for: Self.qtApiServerKey) }
    }

    @Published var questradeAccountNumber: String {
        didSet { KeychainStore.set(questradeAccountNumber, for: Self.qtAccountNumberKey) }
    }

    @Published var questradeAccessTokenExpiry: Date? {
        didSet {
            let value = questradeAccessTokenExpiry.map { String($0.timeIntervalSince1970) } ?? ""
            KeychainStore.set(value, for: Self.qtExpiryKey)
        }
    }

    private init() {
        apiKeyId = KeychainStore.get(Self.keyIdKey) ?? ""
        apiSecretKey = KeychainStore.get(Self.secretKeyKey) ?? ""
        liveTradingAcknowledged = !(KeychainStore.get(Self.liveAckKey) ?? "").isEmpty
        liveApiKeyId = KeychainStore.get(Self.liveKeyIdKey) ?? ""
        liveApiSecretKey = KeychainStore.get(Self.liveSecretKeyKey) ?? ""
        questradeRefreshToken = KeychainStore.get(Self.qtRefreshTokenKey) ?? ""
        questradeAccessToken = KeychainStore.get(Self.qtAccessTokenKey) ?? ""
        questradeApiServer = KeychainStore.get(Self.qtApiServerKey) ?? ""
        questradeAccountNumber = KeychainStore.get(Self.qtAccountNumberKey) ?? ""
        if let raw = KeychainStore.get(Self.qtExpiryKey), let interval = Double(raw) {
            questradeAccessTokenExpiry = Date(timeIntervalSince1970: interval)
        } else {
            questradeAccessTokenExpiry = nil
        }
    }

    var paperCredentials: BrokerCredentials {
        BrokerCredentials(apiKeyId: apiKeyId, apiSecretKey: apiSecretKey, environment: .paper)
    }

    var liveCredentials: BrokerCredentials {
        BrokerCredentials(apiKeyId: liveApiKeyId, apiSecretKey: liveApiSecretKey, environment: .live)
    }

    var questradeCredentials: QuestradeCredentials {
        QuestradeCredentials(accessToken: questradeAccessToken, apiServer: questradeApiServer)
    }

    var isConfigured: Bool {
        paperCredentials.isConfigured
    }

    var isLiveAlpacaConfigured: Bool {
        liveTradingAcknowledged && liveCredentials.isConfigured
    }

    var isQuestradeConfigured: Bool {
        liveTradingAcknowledged && !questradeRefreshToken.isEmpty && !questradeAccountNumber.isEmpty
    }

    var isQuestradeAccessTokenExpired: Bool {
        guard let expiry = questradeAccessTokenExpiry else { return true }
        return Date() >= expiry
    }

    /// All brokerage accounts currently available for placing orders, in the
    /// order they should be offered to the user.
    var availableTradeAccounts: [TradeAccount] {
        var accounts: [TradeAccount] = []
        if isConfigured { accounts.append(.alpacaPaper) }
        if isLiveAlpacaConfigured { accounts.append(.alpacaLive) }
        if isQuestradeConfigured { accounts.append(.questrade(accountNumber: questradeAccountNumber)) }
        return accounts
    }

    func clear() {
        apiKeyId = ""
        apiSecretKey = ""
    }

    func clearLiveAlpaca() {
        liveApiKeyId = ""
        liveApiSecretKey = ""
    }

    func clearQuestrade() {
        questradeRefreshToken = ""
        questradeAccessToken = ""
        questradeApiServer = ""
        questradeAccountNumber = ""
        questradeAccessTokenExpiry = nil
    }

    /// Refreshes the Questrade access token using the stored refresh token,
    /// persisting the rotated refresh token Questrade returns. Must be
    /// called before any Questrade API request if `isQuestradeAccessTokenExpired`.
    func refreshQuestradeToken(client: APIClient) async throws {
        let response = try await client.questradeToken(refreshToken: questradeRefreshToken)
        questradeAccessToken = response.accessToken
        questradeApiServer = response.apiServer
        questradeRefreshToken = response.refreshToken
        questradeAccessTokenExpiry = Date().addingTimeInterval(TimeInterval(response.expiresIn))
    }
}
