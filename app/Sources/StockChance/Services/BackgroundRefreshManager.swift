import Foundation
#if os(iOS)
import BackgroundTasks

/// Periodically wakes the app in the background to check watchlist alerts
/// and position sell-signals against the backend, firing local notifications
/// when something needs attention - so alerts aren't limited to while the
/// app is open with its WebSocket connected.
///
/// This uses iOS's `BGAppRefreshTask`: the system decides when (and whether)
/// to run it based on app usage and battery/network conditions, typically
/// every 15 minutes to a few hours - it's best-effort, not real-time. Unlike
/// true push notifications (which require a paid Apple Developer account for
/// APNs), this works with free/sideloaded signing.
final class BackgroundRefreshManager {
    static let shared = BackgroundRefreshManager()

    static let taskIdentifier = "com.stockchance.app.refresh"

    private init() {}

    /// Registers the background task handler. Must be called before the app
    /// finishes launching (e.g. from the App's `init()`).
    func register() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: Self.taskIdentifier, using: nil) { task in
            self.handle(task: task as! BGAppRefreshTask)
        }
    }

    /// Requests the next background refresh, at least 15 minutes from now.
    func schedule() {
        let request = BGAppRefreshTaskRequest(identifier: Self.taskIdentifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(request)
    }

    private func handle(task: BGAppRefreshTask) {
        // Always schedule the next run before doing any work, so a crash or
        // expiration doesn't leave alerts permanently stuck.
        schedule()

        let work = Task {
            await refresh()
            task.setTaskCompleted(success: true)
        }

        task.expirationHandler = {
            work.cancel()
        }
    }

    private func refresh() async {
        let baseURL = await APIConfig.shared.baseURL
        let client = APIClient(baseURL: baseURL)

        await checkWatchlistAlerts(client: client)
        await checkPositionAlerts(client: client)
    }

    private func checkWatchlistAlerts(client: APIClient) async {
        let alerts = WatchlistAlertStore.shared.alerts.values.filter { $0.isActive }
        for alert in alerts {
            guard !Task.isCancelled else { return }
            guard let signal = try? await client.signal(alert.symbol) else { continue }
            await WatchlistAlertChecker.check(symbol: alert.symbol, price: signal.price, action: signal.action)
        }
    }

    private func checkPositionAlerts(client: APIClient) async {
        let symbols = Set(PositionStore.shared.positions.map(\.symbol))
        for symbol in symbols {
            guard !Task.isCancelled else { return }
            guard let signal = try? await client.daySignal(symbol) else { continue }
            await PositionAlertChecker.check(symbol: symbol, signal: signal)
        }
    }
}
#endif
