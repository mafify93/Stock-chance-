import Foundation

/// Streams JSON messages from one of the backend's WebSocket endpoints
/// (`/ws/watch` for `LiveUpdate`, `/ws/daytrade` for `DayLiveUpdate`).
///
/// Generic over the decoded payload type so a single implementation can
/// serve both the multi-day watchlist stream and the same-day trading
/// stream.
final class WatchStreamService: NSObject {
    private var task: URLSessionWebSocketTask?
    private let decoder = APIClient.decoder

    /// Connects to `path` on `baseURL` (expected to already use the `ws`/`wss`
    /// scheme - see `APIConfig.webSocketBaseURL`) and yields one decoded `T`
    /// per message until cancelled or the connection drops. Reconnects are
    /// the caller's responsibility.
    func updates<T: Decodable>(path: String, symbols: [String], baseURL: URL) -> AsyncThrowingStream<T, Error> {
        AsyncThrowingStream { continuation in
            guard !symbols.isEmpty else {
                continuation.finish()
                return
            }

            var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
            components.queryItems = [URLQueryItem(name: "symbols", value: symbols.joined(separator: ","))]
            guard let url = components.url else {
                continuation.finish(throwing: APIError.server("Invalid WebSocket URL"))
                return
            }

            let session = URLSession(configuration: .default)
            let task = session.webSocketTask(with: url)
            self.task = task
            task.resume()

            func receiveLoop() {
                task.receive { [weak self] result in
                    switch result {
                    case .failure(let error):
                        continuation.finish(throwing: error)
                    case .success(let message):
                        switch message {
                        case .data(let data):
                            self?.decodeAndYield(data, continuation: continuation)
                        case .string(let text):
                            if let data = text.data(using: .utf8) {
                                self?.decodeAndYield(data, continuation: continuation)
                            }
                        @unknown default:
                            break
                        }
                        receiveLoop()
                    }
                }
            }
            receiveLoop()

            continuation.onTermination = { [weak task] _ in
                task?.cancel(with: .goingAway, reason: nil)
            }
        }
    }

    private func decodeAndYield<T: Decodable>(_ data: Data, continuation: AsyncThrowingStream<T, Error>.Continuation) {
        do {
            let update = try decoder.decode(T.self, from: data)
            continuation.yield(update)
        } catch {
            // Ignore malformed individual messages rather than killing the stream.
        }
    }

    func stop() {
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
    }
}
