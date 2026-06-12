import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            TodayView()
                .tabItem { Label("Today", systemImage: "sun.max.fill") }

            WatchlistView()
                .tabItem { Label("Watchlist", systemImage: "star.fill") }

            PositionsView()
                .tabItem { Label("Positions", systemImage: "bag.fill") }

            ScreenerView()
                .tabItem { Label("Screener", systemImage: "chart.bar.fill") }

            SearchView()
                .tabItem { Label("Search", systemImage: "magnifyingglass") }

            SettingsView()
                .tabItem { Label("Settings", systemImage: "gear") }
        }
        .tint(Theme.gold)
    }
}

#Preview {
    ContentView()
        .environmentObject(APIConfig.shared)
}
