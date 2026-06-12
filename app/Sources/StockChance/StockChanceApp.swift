import SwiftUI

@main
struct StockChanceApp: App {
    @StateObject private var apiConfig = APIConfig.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(apiConfig)
        }
        #if os(macOS)
        .defaultSize(width: 900, height: 640)
        #endif
    }
}
