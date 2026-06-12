import Foundation
import UserNotifications

/// Requests permission for, and posts, local notifications when a held
/// position's same-day signal suggests it's time to sell.
@MainActor
final class NotificationManager {
    static let shared = NotificationManager()

    /// Avoids re-notifying for the same alert every poll cycle.
    private var lastNotified: [String: Date] = [:]
    private let cooldown: TimeInterval = 10 * 60

    private init() {}

    func requestAuthorization() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }
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
