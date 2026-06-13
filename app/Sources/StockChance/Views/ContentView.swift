import SwiftUI

struct ContentView: View {
    #if os(iOS)
    @Environment(\.scenePhase) private var scenePhase
    #endif

    var body: some View {
        TabView {
            TodayView()
                .tabItem { Label("Today", systemImage: "sun.max.fill") }

            WatchlistView()
                .tabItem { Label("Watchlist", systemImage: "star.fill") }

            PortfolioView()
                .tabItem { Label("Portfolio", systemImage: "briefcase.fill") }

            ScreenerView()
                .tabItem { Label("Screener", systemImage: "chart.bar.fill") }

            SearchView()
                .tabItem { Label("Search", systemImage: "magnifyingglass") }

            SettingsView()
                .tabItem { Label("Settings", systemImage: "gear") }
        }
        .tint(Theme.gold)
        #if os(iOS)
        .onChange(of: scenePhase) { newPhase in
            if newPhase == .background {
                BackgroundRefreshManager.shared.schedule()
            }
        }
        #endif
    }
}
