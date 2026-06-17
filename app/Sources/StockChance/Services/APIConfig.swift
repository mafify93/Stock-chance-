import Foundation

/// Holds the base URL of the Stock Chance backend (see /backend in the repo).
///
/// Defaults to a local dev server. For a real device or the macOS app you
/// will typically deploy the FastAPI backend (e.g. to Fly.io, Render, or
/// your own server) and change this in Settings.
@MainActor
final class APIConfig: ObservableObject {
    static let shared = APIConfig()

    @Published var baseURL: URL {
        didSet {
            UserDefaults.standard.set(baseURL.absoluteString, forKey: Self.storageKey)
        }
    }

    private static let storageKey = "stockchance.api.baseURL"
    static let defaultURLString = "http://127.0.0.1:8000"

    private init() {
        if let stored = UserDefaults.standard.string(forKey: Self.storageKey),
           let url = URL(string: stored) {
            self.baseURL = url
        } else {
            self.baseURL = URL(string: Self.defaultURLString)!
        }
    }

    var webSocketBaseURL: URL {
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)!
        if components.scheme == "https" {
            components.scheme = "wss"
        } else {
            components.scheme = "ws"
        }
        return components.url!
    }
}
