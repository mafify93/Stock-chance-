import Foundation

enum APIError: LocalizedError {
    case server(String)
    case decoding(Error)
    case transport(Error)

    var errorDescription: String? {
        switch self {
        case .server(let message): return message
        case .decoding(let error): return "Failed to decode response: \(error.localizedDescription)"
        case .transport(let error): return error.localizedDescription
        }
    }
}

/// Thin async/await client for the Stock Chance backend (see /backend).
struct APIClient {
    var baseURL: URL

    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()

    private func get<T: Decodable>(_ path: String, query: [String: String] = [:], headers: [String: String] = [:]) async throws -> T {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = components.url else {
            throw APIError.server("Invalid URL")
        }

        var request = URLRequest(url: url)
        for (key, value) in headers {
            request.setValue(value, forHTTPHeaderField: key)
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw APIError.transport(error)
        }

        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            let message = String(data: data, encoding: .utf8) ?? "HTTP \(http.statusCode)"
            throw APIError.server(message)
        }

        do {
            return try Self.decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(error)
        }
    }

    private func post<T: Decodable, B: Encodable>(_ path: String, body: B, headers: [String: String] = [:]) async throws -> T {
        let url = baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        for (key, value) in headers {
            request.setValue(value, forHTTPHeaderField: key)
        }
        do {
            request.httpBody = try Self.encoder.encode(body)
        } catch {
            throw APIError.decoding(error)
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw APIError.transport(error)
        }

        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            let message = String(data: data, encoding: .utf8) ?? "HTTP \(http.statusCode)"
            throw APIError.server(message)
        }

        do {
            return try Self.decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(error)
        }
    }

    // MARK: - Endpoints

    func search(_ query: String, limit: Int = 15) async throws -> [SearchResult] {
        try await get("/api/search", query: ["q": query, "limit": String(limit)])
    }

    func quote(_ symbol: String) async throws -> Quote {
        try await get("/api/quote/\(symbol)")
    }

    func history(_ symbol: String, period: String = "6mo", interval: String = "1d") async throws -> [Candle] {
        try await get("/api/history/\(symbol)", query: ["period": period, "interval": interval])
    }

    func signal(_ symbol: String) async throws -> SignalResponse {
        try await get("/api/signal/\(symbol)")
    }

    func screener(symbols: [String]? = nil, top: Int = 10) async throws -> ScreenerResponse {
        var query = ["top": String(top)]
        if let symbols, !symbols.isEmpty {
            query["symbols"] = symbols.joined(separator: ",")
        }
        return try await get("/api/screener", query: query)
    }

    // MARK: - Day trading (same-day only)

    func marketSession() async throws -> MarketSession {
        try await get("/api/daytrade/session")
    }

    func daySignal(_ symbol: String) async throws -> DaySignalResponse {
        try await get("/api/daytrade/signal/\(symbol)")
    }

    func intradayHistory(_ symbol: String, period: String = "1d", interval: String = "5m") async throws -> [Candle] {
        try await get("/api/daytrade/intraday/\(symbol)", query: ["period": period, "interval": interval])
    }

    func morningScan(symbols: [String]? = nil, top: Int = 8) async throws -> MorningScanResponse {
        var query = ["top": String(top)]
        if let symbols, !symbols.isEmpty {
            query["symbols"] = symbols.joined(separator: ",")
        }
        return try await get("/api/daytrade/morning", query: query)
    }

    func topPick(symbols: [String]? = nil, count: Int = 3) async throws -> TopPickResponse {
        var query = ["count": String(count)]
        if let symbols, !symbols.isEmpty {
            query["symbols"] = symbols.joined(separator: ",")
        }
        return try await get("/api/daytrade/top-pick", query: query)
    }

    func movers(symbols: [String]? = nil, top: Int = 10) async throws -> MoversResponse {
        var query = ["top": String(top)]
        if let symbols, !symbols.isEmpty {
            query["symbols"] = symbols.joined(separator: ",")
        }
        return try await get("/api/daytrade/movers", query: query)
    }

    // MARK: - Broker (Alpaca paper or live)

    func brokerAccount(credentials: BrokerCredentials) async throws -> BrokerAccount {
        try await get("/api/broker/account", headers: credentials.headers)
    }

    func brokerPositions(credentials: BrokerCredentials) async throws -> [BrokerPosition] {
        try await get("/api/broker/positions", headers: credentials.headers)
    }

    func placeBrokerOrder(_ order: BrokerOrderRequest, credentials: BrokerCredentials) async throws -> BrokerOrder {
        try await post("/api/broker/order", body: order, headers: credentials.headers)
    }

    // MARK: - Broker (Questrade - LIVE, real money)

    func questradeToken(refreshToken: String) async throws -> QuestradeAuthResponse {
        try await post("/api/broker/questrade/token", body: QuestradeTokenRequest(refreshToken: refreshToken))
    }

    func questradeAccounts(credentials: QuestradeCredentials) async throws -> [QuestradeAccount] {
        try await get("/api/broker/questrade/accounts", headers: credentials.headers)
    }

    func questradeBalances(accountNumber: String, credentials: QuestradeCredentials) async throws -> QuestradeBalances {
        try await get("/api/broker/questrade/balances", query: ["account_number": accountNumber], headers: credentials.headers)
    }

    func questradeSymbols(_ query: String, credentials: QuestradeCredentials) async throws -> [QuestradeSymbol] {
        try await get("/api/broker/questrade/symbols", query: ["q": query], headers: credentials.headers)
    }

    func placeQuestradeOrder(_ order: QuestradeOrderRequest, credentials: QuestradeCredentials) async throws -> QuestradeOrder {
        try await post("/api/broker/questrade/order", body: order, headers: credentials.headers)
    }
}

/// Alpaca API credentials, kept in the Keychain and sent per-request - the
/// backend never stores them. `environment` selects between Alpaca's
/// simulated paper account and the user's REAL live account.
struct BrokerCredentials {
    var apiKeyId: String
    var apiSecretKey: String
    var environment: BrokerEnvironment = .paper

    var headers: [String: String] {
        ["Apca-Api-Key-Id": apiKeyId, "Apca-Api-Secret-Key": apiSecretKey, "Apca-Api-Env": environment.rawValue]
    }

    var isConfigured: Bool {
        !apiKeyId.isEmpty && !apiSecretKey.isEmpty
    }
}

/// Questrade OAuth credentials for the user's **live** brokerage account,
/// kept in the Keychain and sent per-request.
struct QuestradeCredentials {
    var accessToken: String
    var apiServer: String

    var headers: [String: String] {
        ["Questrade-Access-Token": accessToken, "Questrade-Api-Server": apiServer]
    }

    var isConfigured: Bool {
        !accessToken.isEmpty && !apiServer.isEmpty
    }
}
