import Foundation

/// Checks a held position's latest same-day signal for a take-profit /
/// stop-loss / end-of-day-exit alert, or a flip to "Sell Now", and fires a
/// local notification. Shared by the live WebSocket view model and the
/// background refresh task.
enum PositionAlertChecker {
    @MainActor
    static func check(symbol: String, signal: DaySignalResponse) {
        let price = signal.price.formatted(.currency(code: "USD"))
        if let alert = signal.alert {
            NotificationManager.shared.notify(
                key: "\(symbol)-\(alert.rawValue)",
                title: "\(symbol): \(alert.label)",
                body: "Now trading at \(price)."
            )
        } else if signal.action == .daySell {
            NotificationManager.shared.notify(
                key: "\(symbol)-SELL_NOW",
                title: "\(symbol): Sell Now signal",
                body: "The same-day signal flipped to Sell Now at \(price)."
            )
        }
    }
}
