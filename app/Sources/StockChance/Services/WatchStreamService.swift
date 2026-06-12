import Foundation

/// Streams live quote + buy/sell/hold signal updates from the backend's
/// `/ws/watch` WebSocket endpoint.
final class WatchStreamService: NSObject {
    private var task: URLSessionWebSocketTask?
    private let decoder = APIClient.decoder

    /// Connects and yields one `LiveUpdate` per message until cancelled or
    /// the connection drops. Reconnects are the caller's responsibility.
    func updates(for symbols: [String], baseURL: URL) -> AsyncThrowingStream<LiveUpdate, Error> {
        AsyncThrowingStream { continuation in
            guard !symbols.isEmpty else {
                continuation.finish()
                return
            }

            var components = URLComponents(url: baseURL.appendingPathComponent("/ws/watch"), resolvingAgainstBaseURL: false)!
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

    private func decodeAndYield(_ data: Data, continuation: AsyncThrowingStream<LiveUpdate, Error>.Continuation) {
        do {
            let update = try decoder.decode(LiveUpdate.self, from: data)
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
