import SwiftUI

struct ContentView: View {
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
    }
}
