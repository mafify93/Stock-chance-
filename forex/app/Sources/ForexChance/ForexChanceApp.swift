import SwiftUI

@main
struct ForexChanceApp: App {
    @StateObject private var apiConfig = APIConfig.shared
    @StateObject private var brokerStore = BrokerStore.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(apiConfig)
                .environmentObject(brokerStore)
        }
        #if os(macOS)
        .defaultSize(width: 920, height: 660)
        #endif
    }
}
