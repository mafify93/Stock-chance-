import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var apiConfig: APIConfig
    @EnvironmentObject private var brokerStore: BrokerStore

    var body: some View {
        TabView {
            TodayView()
                .tabItem { Label("Today", systemImage: "sun.max.fill") }

            MarketsView()
                .tabItem { Label("Markets", systemImage: "list.bullet") }

            ScreenerView()
                .tabItem { Label("Screener", systemImage: "chart.bar.fill") }

            AutoTraderView(baseURL: apiConfig.baseURL, brokerStore: brokerStore)
                .tabItem { Label("Auto", systemImage: "bolt.fill") }

            PositionsView()
                .tabItem { Label("Positions", systemImage: "briefcase.fill") }

            SettingsView()
                .tabItem { Label("Settings", systemImage: "gearshape.fill") }
        }
        .tint(Theme.accent)
        .preferredColorScheme(.dark)
    }
}

/// Wraps screen content in the app's dark gradient background.
struct ScreenBackground<Content: View>: View {
    private let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        ZStack {
            Theme.backgroundGradient.ignoresSafeArea()
            content
        }
    }
}
