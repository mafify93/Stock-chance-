import Foundation

/// Which OANDA environment to trade against.
enum OandaEnvironment: String, CaseIterable, Identifiable {
    case practice
    case live

    var id: String { rawValue }

    var label: String {
        switch self {
        case .practice: return "Practice (Demo)"
        case .live: return "Live (Real Money)"
        }
    }

    /// Whether orders placed in this environment use real money.
    var isLive: Bool { self == .live }
}

/// The OANDA credentials needed for one request, packaged for the API client.
struct OandaCredentials {
    var token: String
    var accountId: String
    var environment: OandaEnvironment

    var isConfigured: Bool { !token.isEmpty && !accountId.isEmpty }
}

/// Holds the user's OANDA credentials in the Keychain.
///
/// Credentials are never written to UserDefaults, never bundled with the app,
/// and never stored by the backend - they're sent with each request. The
/// practice (demo) environment is safe to use freely; **live** trading is only
/// used once the user has explicitly acknowledged that it places real orders
/// with real money (`liveTradingAcknowledged`).
@MainActor
final class BrokerStore: ObservableObject {
    static let shared = BrokerStore()

    private static let tokenKey = "oanda.apiToken"
    private static let accountKey = "oanda.accountId"
    private static let liveTokenKey = "oanda.live.apiToken"
    private static let liveAccountKey = "oanda.live.accountId"
    private static let liveAckKey = "oanda.liveTradingAcknowledged"

    // Practice (demo - virtual money)
    @Published var token: String {
        didSet { KeychainStore.set(token, for: Self.tokenKey) }
    }
    @Published var accountId: String {
        didSet { KeychainStore.set(accountId, for: Self.accountKey) }
    }

    // Live (REAL money)
    @Published var liveToken: String {
        didSet { KeychainStore.set(liveToken, for: Self.liveTokenKey) }
    }
    @Published var liveAccountId: String {
        didSet { KeychainStore.set(liveAccountId, for: Self.liveAccountKey) }
    }
    @Published var liveTradingAcknowledged: Bool {
        didSet { KeychainStore.set(liveTradingAcknowledged ? "1" : "", for: Self.liveAckKey) }
    }

    private init() {
        token = KeychainStore.get(Self.tokenKey) ?? ""
        accountId = KeychainStore.get(Self.accountKey) ?? ""
        liveToken = KeychainStore.get(Self.liveTokenKey) ?? ""
        liveAccountId = KeychainStore.get(Self.liveAccountKey) ?? ""
        liveTradingAcknowledged = !(KeychainStore.get(Self.liveAckKey) ?? "").isEmpty
    }

    var practiceCredentials: OandaCredentials {
        OandaCredentials(token: token, accountId: accountId, environment: .practice)
    }

    var liveCredentials: OandaCredentials {
        OandaCredentials(token: liveToken, accountId: liveAccountId, environment: .live)
    }

    var isPracticeConfigured: Bool { practiceCredentials.isConfigured }

    var isLiveConfigured: Bool { liveTradingAcknowledged && liveCredentials.isConfigured }

    /// Credentials for the given environment.
    func credentials(for environment: OandaEnvironment) -> OandaCredentials {
        environment == .live ? liveCredentials : practiceCredentials
    }

    /// The environments currently usable for data and trading, in display order.
    var availableEnvironments: [OandaEnvironment] {
        var envs: [OandaEnvironment] = []
        if isPracticeConfigured { envs.append(.practice) }
        if isLiveConfigured { envs.append(.live) }
        return envs
    }

    /// The best credentials to use for read-only data requests (signals,
    /// quotes, charts): practice if configured, else live.
    var dataCredentials: OandaCredentials? {
        if isPracticeConfigured { return practiceCredentials }
        if isLiveConfigured { return liveCredentials }
        return nil
    }

    func clearPractice() {
        token = ""
        accountId = ""
    }

    func clearLive() {
        liveToken = ""
        liveAccountId = ""
    }
}
