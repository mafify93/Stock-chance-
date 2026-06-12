# Stock Chance (iOS & macOS)

A SwiftUI multiplatform app (iOS 17+ / macOS 14+) for day-trading-style
decision support: watchlist with live price + Buy/Sell/Hold signals, a
screener for "what to buy / what to sell right now", per-stock charts,
indicator breakdowns, and analyst price targets - all backed by the free
[Stock Chance API](../backend).

## ⚠️ Disclaimer

This app surfaces **technical-analysis signals**, not guaranteed
predictions. Markets are risky. Nothing in this app is financial advice.

## Project structure

```
app/
  project.yml                 # XcodeGen project definition
  Sources/StockChance/
    StockChanceApp.swift      # App entry point
    Models/Models.swift       # Codable models matching the backend API
    Services/
      APIConfig.swift          # Backend base URL (configurable in Settings)
      APIClient.swift          # REST client (search/quote/history/signal/screener)
      WatchStreamService.swift # WebSocket client for live updates
      WatchlistStore.swift     # Persisted watchlist (UserDefaults)
    ViewModels/                # @Observable view models
    Views/
      ContentView.swift         # Root TabView (Watchlist / Screener / Search / Settings)
      WatchlistView.swift       # Live watchlist with signal badges
      ScreenerView.swift        # "What to buy / what to sell" rankings
      SearchView.swift          # Search any symbol (Yahoo Finance universe)
      StockDetailView.swift     # Chart, signal breakdown, levels, analyst outlook
      SettingsView.swift        # Backend URL configuration
    Resources/                  # Assets.xcassets, macOS entitlements
```

## Building

This repo doesn't commit a generated `.xcodeproj` (it's environment-specific
and easy to regenerate). On a Mac:

1. Install [XcodeGen](https://github.com/yonaskolb/XcodeGen):
   ```bash
   brew install xcodegen
   ```
2. Generate the Xcode project:
   ```bash
   cd app
   xcodegen generate
   ```
3. Open `StockChance.xcodeproj` in Xcode.
4. Select the **StockChance (macOS)** or **StockChance (iOS)** scheme and
   run.
5. In Xcode, set your Team under *Signing & Capabilities* for both targets
   if you want to run on a physical device.

## Connecting to the backend

By default the app points at `http://127.0.0.1:8000` (see
[Stock Chance API](../backend)).

- **iOS Simulator / Mac app**: run the backend locally
  (`uvicorn app.main:app --reload`) - `127.0.0.1` works as-is.
- **Physical iPhone**: use your computer's LAN IP (e.g.
  `http://192.168.1.50:8000`) or deploy the backend to a public host, then
  update the URL in the app's **Settings** tab.

Local HTTP (non-HTTPS) traffic to `localhost`/LAN is allowed via
`NSAllowsLocalNetworking` in Info.plist for development. For a deployed
backend, use HTTPS.

## Features

1. **Watchlist** - add any symbol via search; live price + Buy/Sell/Hold
   badge streamed over WebSocket every ~15s.
2. **Screener** - ranks a curated set of popular stocks/ETFs (or your
   watchlist) into Buy / Sell / Hold buckets.
3. **Stock detail** - price chart with 50-day moving average overlay,
   composite signal score with full reasoning (which indicators fired and
   why), suggested entry/stop-loss/take-profit (ATR-based), and free analyst
   price targets when available.
4. **Search** - any stock/ETF/index/crypto/FX symbol available on Yahoo
   Finance.
5. **Settings** - configure and test the backend connection.
