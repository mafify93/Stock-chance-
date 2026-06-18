import Foundation

enum APIError: LocalizedError {
    case server(status: Int, message: String)
    case decoding(Error)
    case transport(Error)
    case notConfigured

    var errorDescription: String? {
        switch self {
        case .server(_, let message): return message
        case .decoding(let error): return "Failed to decode response: \(error.localizedDescription)"
        case .transport(let error): return error.localizedDescription
        case .notConfigured: return "Add your OANDA API token and account ID in Settings > Broker."
        }
    }
}

/// Thin async/await client for the Forex Chance backend (see /forex/backend).
///
/// OANDA credentials are passed per-request as headers - the backend never
/// stores them. Data endpoints (signals, quotes, charts) need a token +
/// account ID; trading endpoints need them too, with `Oanda-Api-Env`
/// selecting the practice/live environment.
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

    private static func headers(for creds: OandaCredentials) -> [String: String] {
        [
            "Oanda-Api-Token": creds.token,
            "Oanda-Account-Id": creds.accountId,
            "Oanda-Api-Env": creds.environment.rawValue,
        ]
    }

    // MARK: - Core requests

    private func get<T: Decodable>(_ path: String, query: [String: String] = [:], headers: [String: String] = [:]) async throws -> T {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = components.url else {
            throw APIError.server(status: 0, message: "Invalid URL")
        }

        var request = URLRequest(url: url)
        // Generous timeout so a multi-pair scan or a cold-starting free-tier
        // host (which can take 30-60s to wake) doesn't fail.
        request.timeoutInterval = 120
        for (key, value) in headers { request.setValue(value, forHTTPHeaderField: key) }

        return try await send(request)
    }

    private func send<T: Decodable, B: Encodable>(_ path: String, method: String, body: B, headers: [String: String] = [:]) async throws -> T {
        let url = baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        for (key, value) in headers { request.setValue(value, forHTTPHeaderField: key) }
        do {
            request.httpBody = try Self.encoder.encode(body)
        } catch {
            throw APIError.decoding(error)
        }
        return try await send(request)
    }

    private func send<T: Decodable>(_ request: URLRequest) async throws -> T {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw APIError.transport(error)
        }

        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            var message = "HTTP \(http.statusCode)"
            if let detail = try? Self.decoder.decode(ErrorDetail.self, from: data) {
                message = detail.detail
            } else if let text = String(data: data, encoding: .utf8), !text.isEmpty {
                message = text
            }
            throw APIError.server(status: http.statusCode, message: message)
        }

        do {
            return try Self.decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(error)
        }
    }

    private struct ErrorDetail: Decodable { var detail: String }

    // MARK: - Pairs & data (read-only)

    func pairs(filter: String? = nil) async throws -> [PairInfo] {
        var query: [String: String] = [:]
        if let filter, !filter.isEmpty { query["q"] = filter }
        return try await get("/api/pairs", query: query)
    }

    func quote(_ pair: String, creds: OandaCredentials) async throws -> PairQuote {
        try await get("/api/quote/\(pair)", headers: Self.headers(for: creds))
    }

    func candles(_ pair: String, granularity: String = "H1", count: Int = 300, creds: OandaCredentials) async throws -> [Candle] {
        try await get("/api/candles/\(pair)", query: ["granularity": granularity, "count": String(count)], headers: Self.headers(for: creds))
    }

    func signal(_ pair: String, granularity: String = "H1", creds: OandaCredentials) async throws -> SignalResponse {
        try await get("/api/signal/\(pair)", query: ["granularity": granularity], headers: Self.headers(for: creds))
    }

    func screener(pairs: [String]? = nil, top: Int = 10, creds: OandaCredentials) async throws -> ScreenerResponse {
        var query = ["top": String(top)]
        if let pairs, !pairs.isEmpty { query["pairs"] = pairs.joined(separator: ",") }
        return try await get("/api/screener", query: query, headers: Self.headers(for: creds))
    }

    // MARK: - Day trading

    func marketSession() async throws -> MarketSession {
        try await get("/api/daytrade/session")
    }

    func daySignal(_ pair: String, creds: OandaCredentials) async throws -> DaySignalResponse {
        try await get("/api/daytrade/signal/\(pair)", headers: Self.headers(for: creds))
    }

    func intradayCandles(_ pair: String, granularity: String = "M5", count: Int = 300, creds: OandaCredentials) async throws -> [Candle] {
        try await get("/api/daytrade/intraday/\(pair)", query: ["granularity": granularity, "count": String(count)], headers: Self.headers(for: creds))
    }

    func topPick(pairs: [String]? = nil, count: Int = 3, creds: OandaCredentials) async throws -> TopPickResponse {
        var query = ["count": String(count)]
        if let pairs, !pairs.isEmpty { query["pairs"] = pairs.joined(separator: ",") }
        return try await get("/api/daytrade/top-pick", query: query, headers: Self.headers(for: creds))
    }

    // MARK: - Broker (OANDA)

    func account(creds: OandaCredentials) async throws -> BrokerAccount {
        try await get("/api/broker/account", headers: Self.headers(for: creds))
    }

    func positions(creds: OandaCredentials) async throws -> [BrokerPosition] {
        try await get("/api/broker/positions", headers: Self.headers(for: creds))
    }

    func placeOrder(_ order: BrokerOrderRequest, creds: OandaCredentials) async throws -> BrokerOrder {
        try await send("/api/broker/order", method: "POST", body: order, headers: Self.headers(for: creds))
    }

    func closePosition(_ request: CloseRequest, creds: OandaCredentials) async throws -> CloseResponse {
        try await send("/api/broker/close", method: "POST", body: request, headers: Self.headers(for: creds))
    }
}
