import Foundation
import UserNotifications

/// Requests permission for, and posts, local notifications - sell alerts for
/// held positions, and price/signal alerts for watched symbols.
@MainActor
final class NotificationManager: NSObject {
    static let shared = NotificationManager()

    /// Avoids re-notifying for the same alert every poll cycle.
    private var lastNotified: [String: Date] = [:]
    private let cooldown: TimeInterval = 10 * 60

    private override init() {
        super.init()
        // Without a delegate, iOS silently drops local notifications while
        // the app is in the foreground - set ourselves as the delegate so
        // alerts still show as a banner even if Stock Chance is open.
        UNUserNotificationCenter.current().delegate = self
    }

    func requestAuthorization() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }
    }

    /// Current system notification permission, so Settings can show whether
    /// alerts are actually able to display and offer a way to fix it.
    func authorizationStatus() async -> UNAuthorizationStatus {
        await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
    }

    func notify(key: String, title: String, body: String) {
        let now = Date()
        if let last = lastNotified[key], now.timeIntervalSince(last) < cooldown {
            return
        }
        lastNotified[key] = now

        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default

        let request = UNNotificationRequest(identifier: "\(key)-\(now.timeIntervalSince1970)", content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }
}

extension NotificationManager: UNUserNotificationCenterDelegate {
    /// Shows the banner/sound/list entry even while Stock Chance is open and
    /// in the foreground.
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound, .badge, .list])
    }
}
