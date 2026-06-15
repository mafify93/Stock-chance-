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

            AutoTraderView()
                .tabItem { Label("Auto Trade", systemImage: "bolt.fill") }

            SettingsView()
                .tabItem { Label("Settings", systemImage: "gear") }
        }
        .tint(Theme.gold)
        // Pin a light appearance so system controls (Form section headers,
        // pickers, the tab bar) always match the light theme, regardless of
        // the device's system-wide Dark Mode setting.
        .preferredColorScheme(.light)
        .task {
            NotificationManager.shared.requestAuthorization()
        }
        #if os(iOS)
        .onChange(of: scenePhase) { newPhase in
            if newPhase == .background {
                BackgroundRefreshManager.shared.schedule()
            }
        }
        #endif
    }
}
