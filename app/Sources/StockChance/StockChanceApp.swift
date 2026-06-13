import SwiftUI

@main
struct StockChanceApp: App {
    @StateObject private var apiConfig = APIConfig.shared
    @StateObject private var brokerStore = BrokerStore.shared

    init() {
        #if os(iOS)
        BackgroundRefreshManager.shared.register()
        BackgroundRefreshManager.shared.schedule()
        #endif
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(apiConfig)
                .environmentObject(brokerStore)
        }
        #if os(macOS)
        .defaultSize(width: 900, height: 640)
        #endif
    }
}
