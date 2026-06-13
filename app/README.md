# Stock Chance (iOS & macOS)

A SwiftUI multiplatform app (iOS 17+ / macOS 14+) for day-trading-style
decision support: a "Today" morning watchlist of same-day buy/watch/avoid
candidates, a premium live watchlist with Buy/Sell/Hold signals and
configurable price/signal alerts, a screener for "what to buy / what to sell
right now", a Portfolio tab combining "I bought this" position tracking
(live P/L, sell alerts, trade journal) with connected brokerage account
balances, per-stock daily + intraday charts, indicator breakdowns, a
strategy backtester, and analyst price targets - all backed by the free
[Stock Chance API](../backend), wrapped in a dark "private trading terminal"
theme.

## ⚠️ Disclaimer

This app surfaces **technical-analysis signals**, not guaranteed
predictions. Markets are risky. Nothing in this app is financial advice.

## Project structure

```
app/
  project.yml                 # XcodeGen project definition
  Sources/StockChance/
    StockChanceApp.swift      # App entry point
    Theme.swift                # Dark "private trading terminal" theme (colors, fonts, card/button styles)
    Models/Models.swift       # Codable models matching the backend API
    Services/
      APIConfig.swift          # Backend base URL (configurable in Settings)
      APIClient.swift          # REST client (search/quote/history/signal/screener/daytrade/backtest/broker)
      WatchStreamService.swift # Generic WebSocket client (/ws/watch and /ws/daytrade)
      WatchlistStore.swift     # Persisted watchlist (UserDefaults)
      WatchlistAlertStore.swift # Persisted per-symbol price/signal alerts (UserDefaults)
      PositionStore.swift      # Persisted "I bought this" positions (UserDefaults)
      JournalStore.swift       # Persisted trade journal (UserDefaults)
      BrokerStore.swift        # Brokerage credentials (Alpaca paper/live, Questrade) (Keychain)
      NotificationManager.swift # Local notifications for sell/price/signal alerts
    ViewModels/                # @Observable view models
    Views/
      ContentView.swift         # Root TabView (Today / Watchlist / Portfolio / Screener / Search / Settings)
      TodayView.swift           # Morning watchlist: market session + Buy at Open / Watch / Avoid
      WatchlistView.swift       # Premium live watchlist with signal badges and price/signal alerts
      PortfolioView.swift       # "I bought this" positions + connected broker account balances + journal link
      JournalView.swift         # Trade journal: logged orders, realized P/L, win rate
      BacktestView.swift        # Walk-forward backtest of the signal engine vs buy-and-hold
      ScreenerView.swift        # "What to buy / what to sell" rankings
      SearchView.swift          # Search any symbol (Yahoo Finance universe)
      StockDetailView.swift     # Daily + intraday charts, signal breakdown, levels, analyst outlook, "I Bought This"
      MarketSessionBanner.swift # Pre-market/open/after-hours/closed banner
      SignalBadge.swift          # Buy/Sell/Hold badges and alert banners
      SettingsView.swift        # Backend URL + broker credentials configuration
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

1. **Today** - the morning watchlist: current market session (pre-market /
   open / after-hours / closed, with a countdown), plus Buy at Open / Watch
   for a Dip / Avoid Today candidates with a plain-English plan and suspected
   profit estimate for each.
2. **Watchlist** - add any symbol via search; live price + Buy/Sell/Hold
   badge streamed over WebSocket every ~15s, shown in premium signal-tinted
   cards. Swipe a row to set a price-above/price-below or signal-change
   alert (local notification, bell icon shows when one is active).
3. **Portfolio** - mark a stock as "I Bought This" (entry price + quantity)
   from its detail screen, then track live current price, unrealized P/L, and
   same-day sell alerts here, with local notifications when it's time to
   sell. Logging a "Sold" exit price records the realized P/L to the **Trade
   Journal**. Also shows a summary (equity/cash/buying power/positions) for
   every connected brokerage account (Alpaca paper/live, Questrade).
4. **Trade Journal** (from Portfolio) - history of every broker order placed
   through Stock Chance plus logged position exits, with running win rate and
   total realized P/L.
5. **Screener** - ranks a curated set of popular stocks/ETFs (or your
   watchlist) into Buy / Sell / Hold buckets.
6. **Stock detail** - daily price chart with 50-day moving average overlay,
   composite signal score with full reasoning (which indicators fired and
   why), suggested entry/stop-loss/take-profit (ATR-based), free analyst price
   targets when available, a **Backtest** link showing how the signal
   strategy performed historically vs. buy-and-hold, plus a **Day Trade
   Signal** card with an intraday (5-minute) chart, VWAP/entry/target/stop
   lines, and live alerts.
7. **Search** - any stock/ETF/index/crypto/FX symbol available on Yahoo
   Finance.
8. **Settings** - configure and test the backend connection, plus broker
   credentials (Alpaca paper/live, Questrade).
