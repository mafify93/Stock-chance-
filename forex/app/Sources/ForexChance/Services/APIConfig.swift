import Foundation

/// Holds the base URL of the Forex Chance backend (see /forex/backend).
///
/// Defaults to a local dev server. For a real device or the macOS app you
/// will typically deploy the FastAPI backend (e.g. to Render) and change
/// this in Settings.
@MainActor
final class APIConfig: ObservableObject {
    static let shared = APIConfig()

    @Published var baseURL: URL {
        didSet {
            UserDefaults.standard.set(baseURL.absoluteString, forKey: Self.storageKey)
        }
    }

    private static let storageKey = "forexchance.api.baseURL"
    static let defaultURLString = "http://127.0.0.1:8000"

    private init() {
        if let stored = UserDefaults.standard.string(forKey: Self.storageKey),
           let url = URL(string: stored) {
            self.baseURL = url
        } else {
            self.baseURL = URL(string: Self.defaultURLString)!
        }
    }
}
