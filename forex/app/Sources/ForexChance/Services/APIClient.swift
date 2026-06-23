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

/// True when an error is just a cancelled request (view disappeared, task
/// superseded) rather than a real failure. View models use this to avoid
/// showing a scary "cancelled" message for a request the user implicitly
/// abandoned.
func isCancellation(_ error: Error) -> Bool {
    if error is CancellationError { return true }
    if let urlError = error as? URLError, urlError.code == .cancelled { return true }
    if let apiError = error as? APIError, case .transport(let underlying) = apiError {
        return isCancellation(underlying)
    }
    return false
}

/// Transport errors worth retrying once the free-tier backend has had a
/// moment to wake up from a cold start. Cancellations are deliberately
/// excluded so abandoned requests aren't retried.
private func isRetryableTransport(_ error: Error) -> Bool {
    guard let urlError = error as? URLError else { return false }
    switch urlError.code {
    case .timedOut, .cannotConnectToHost, .cannotFindHost,
         .networkConnectionLost, .dnsLookupFailed, .badServerResponse:
        return true
    default:
        return false
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
        guard var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false) else {
            throw APIError.server(status: 0, message: "Invalid backend URL. Check Settings > Backend.")
        }
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

        // GETs are idempotent, so retry a couple of times to ride out a
        // free-tier backend waking from sleep.
        return try await send(request, retries: 2)
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

    private func send<T: Decodable>(_ request: URLRequest, retries: Int = 0) async throws -> T {
        var attempt = 0
        while true {
            do {
                let (data, response) = try await URLSession.shared.data(for: request)

                if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                    // Gateway errors usually mean the free-tier host is still
                    // waking up; give it a moment and try again.
                    if attempt < retries, [502, 503, 504].contains(http.statusCode) {
                        attempt += 1
                        try? await Task.sleep(nanoseconds: Self.backoffNanos(attempt))
                        continue
                    }
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
            } catch let error as APIError {
                throw error  // already classified (server/decoding) - don't retry
            } catch {
                // Transport-level failure from URLSession.
                if attempt < retries, isRetryableTransport(error) {
                    attempt += 1
                    try? await Task.sleep(nanoseconds: Self.backoffNanos(attempt))
                    continue
                }
                throw APIError.transport(error)
            }
        }
    }

    /// Exponential backoff: ~1s, 2s, 4s.
    private static func backoffNanos(_ attempt: Int) -> UInt64 {
        let seconds = pow(2.0, Double(max(0, attempt - 1)))
        return UInt64(seconds * 1_000_000_000)
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

    // MARK: - Auto-Trader

    func autoTraderStatus() async throws -> AutoTraderStatus {
        try await get("/api/autotrader/status")
    }

    func startAutoTrader(_ request: AutoTraderStartRequest) async throws -> [String: String] {
        try await send("/api/autotrader/start", method: "POST", body: request)
    }

    func stopAutoTrader() async throws -> [String: String] {
        struct Empty: Encodable {}
        return try await send("/api/autotrader/stop", method: "POST", body: Empty())
    }

    /// Live-tune the running bot's config without restarting it.
    func updateAutoTraderConfig(_ patch: AutoTraderConfigPatch) async throws {
        struct Ack: Decodable {}
        let _: Ack = try await send("/api/autotrader/config", method: "PATCH", body: patch)
    }

    func emergencyClose() async throws -> [String: [String]] {
        struct Empty: Encodable {}
        return try await send("/api/autotrader/emergency-close", method: "POST", body: Empty())
    }

    func resetDay() async throws {
        struct Empty: Encodable {}
        struct Ack2: Decodable {}
        let _: Ack2 = try await send("/api/autotrader/reset-day", method: "POST", body: Empty())
    }

    func learnerStats() async throws -> LearnerStats {
        try await get("/api/autotrader/learner-stats")
    }

    func backtest(_ request: BacktestRequest) async throws -> BacktestResult {
        try await send("/api/autotrader/backtest", method: "POST", body: request)
    }
}
