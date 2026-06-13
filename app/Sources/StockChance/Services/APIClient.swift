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

    private func get<T: Decodable>(_ path: String, query: [String: String] = [:]) async throws -> T {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = components.url else {
            throw APIError.server("Invalid URL")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(from: url)
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
}
