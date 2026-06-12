import Foundation
import Observation

/// Persists the user's "I bought this" positions to UserDefaults so the
/// Positions tab can track live P/L and surface same-day sell alerts.
@Observable
final class PositionStore {
    static let shared = PositionStore()

    private static let storageKey = "stockchance.positions"

    var positions: [Position] {
        didSet {
            save()
        }
    }

    private init() {
        if let data = UserDefaults.standard.data(forKey: Self.storageKey),
           let decoded = try? JSONDecoder().decode([Position].self, from: data) {
            self.positions = decoded
        } else {
            self.positions = []
        }
    }

    private func save() {
        if let data = try? JSONEncoder().encode(positions) {
            UserDefaults.standard.set(data, forKey: Self.storageKey)
        }
    }

    func add(symbol: String, entryPrice: Double, quantity: Double) {
        positions.append(Position(symbol: symbol.uppercased(), entryPrice: entryPrice, quantity: quantity, boughtAt: Date()))
    }

    func remove(_ position: Position) {
        positions.removeAll { $0.id == position.id }
    }

    func removeAll(symbol: String) {
        positions.removeAll { $0.symbol == symbol.uppercased() }
    }

    func contains(symbol: String) -> Bool {
        positions.contains { $0.symbol == symbol.uppercased() }
    }
}
