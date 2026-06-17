import Foundation

/// Checks a watched symbol's latest price/signal against its user-configured
/// alert and fires a local notification if it crosses a price threshold or
/// its signal action just changed. Shared by the live WebSocket view model
/// and the background refresh task, so alerts fire the same way whether the
/// app is open or in the background.
enum WatchlistAlertChecker {
    @MainActor
    static func check(symbol: String, price: Double?, currency: String = "USD", action: TradeAction?) {
        guard let alert = WatchlistAlertStore.shared.alert(for: symbol), alert.isActive else { return }

        if let price {
            if let above = alert.priceAbove, price >= above {
                NotificationManager.shared.notify(
                    key: "watchlist-price-above-\(symbol)",
                    title: "\(symbol) is above \(above.formatted(.currency(code: currency)))",
                    body: "Now trading at \(price.formatted(.currency(code: currency)))."
                )
            }
            if let below = alert.priceBelow, price <= below {
                NotificationManager.shared.notify(
                    key: "watchlist-price-below-\(symbol)",
                    title: "\(symbol) is below \(below.formatted(.currency(code: currency)))",
                    body: "Now trading at \(price.formatted(.currency(code: currency)))."
                )
            }
        }

        if alert.notifyOnSignalChange, let action {
            if let previous = alert.lastSignalAction, previous != action {
                NotificationManager.shared.notify(
                    key: "watchlist-signal-\(symbol)-\(action.rawValue)",
                    title: "\(symbol) signal changed to \(action.label)",
                    body: "The technical signal for \(symbol) just changed to \(action.label)."
                )
            }
            if alert.lastSignalAction != action {
                WatchlistAlertStore.shared.updateLastSignalAction(action, for: symbol)
            }
        }
    }
}
