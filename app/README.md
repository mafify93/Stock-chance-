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
      WatchlistAlertChecker.swift # Shared watchlist alert-matching logic (live + background)
      PositionStore.swift      # Persisted "I bought this" positions (UserDefaults)
      PositionAlertChecker.swift # Shared position sell-alert logic (live + background)
      JournalStore.swift       # Persisted trade journal (UserDefaults)
      BrokerStore.swift        # Brokerage credentials (Alpaca paper/live, Questrade) (Keychain)
      NotificationManager.swift # Local notifications for sell/price/signal alerts
      BackgroundRefreshManager.swift # iOS background refresh: checks alerts when the app isn't open
    ViewModels/                # @Observable view models
    Views/
      ContentView.swift         # Root TabView (Today / Watchlist / Portfolio / Screener / Auto Trade / Settings)
      TodayView.swift           # Morning watchlist: market session + Tonight's Picks + Buy at Open / Watch / Avoid
      WatchlistView.swift       # Premium live watchlist with signal badges and price/signal alerts
      PortfolioView.swift       # "I bought this" positions + connected broker account balances + journal link
      JournalView.swift         # Trade journal: logged orders, realized P/L, win rate
      BacktestView.swift        # Walk-forward backtest of the signal engine vs buy-and-hold
      ScreenerView.swift        # "What to buy / what to sell" rankings
      SearchView.swift          # Search any symbol (Yahoo Finance universe) - presented from Watchlist's "+" button
      ExpandableText.swift      # Collapsible "Read more" text used for long AI summaries/plans
      StockDetailView.swift     # Daily + intraday charts, signal breakdown, levels, analyst outlook, AI Insight, "I Bought This"
      MarketSessionBanner.swift # Pre-market/open/after-hours/closed banner
      SignalBadge.swift          # Buy/Sell/Hold badges and alert banners
      AutoTraderView.swift      # "Auto Trade" tab: AI Auto-Trader configuration, safety confirmations, and decision log
      SettingsView.swift        # Backend URL, broker credentials, and notification permissions
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
   open / after-hours / closed, with a countdown), a **Tonight's Picks** card
   showing the AI's overnight deep-research shortlist of what to consider
   buying at the next open (with the news catalyst and a plan for each pick -
   see [AI features](#ai-features) below), plus Buy at Open / Watch for a Dip
   / Avoid Today candidates with a plain-English plan and suspected profit
   estimate for each.
2. **Watchlist** - add any symbol via search; live price + Buy/Sell/Hold
   badge streamed over WebSocket every ~15s, shown in premium signal-tinted
   cards. Swipe a row to set a price-above/price-below or signal-change
   alert (local notification, bell icon shows when one is active). Alerts are
   checked live while the app is open, and periodically in the background
   (iOS Background App Refresh) so they still fire when the app is closed -
   see [Background alerts](#background-alerts) below.
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
   Finance, via the "+" button on the Watchlist tab.
8. **AI Insight** (in Stock detail) - a combined recommendation from the
   rule-based signal, a machine-learning model trained on years of price
   history (probability the price is higher in 5 trading days), and -
   optionally - an AI analyst's plain-English summary. Hidden automatically if
   the backend has no trained model and no AI analyst configured.
9. **Auto Trade** (its own tab) - configure an autonomous trading loop that
   uses the same combined AI recommendation to place orders through Alpaca:
   pick symbols, a minimum confidence threshold, max position size, daily
   trade cap, and check frequency. **Disabled by default.** Real-money trading
   requires switching to the "Live" environment *and* a separate "Confirm
   Real-Money Trading" toggle, each with its own warning. Shows a log of
   recent decisions (including HOLDs and skipped trades with the reason why).
10. **Tonight's Picks** (top of Today) - every evening, the backend has Claude
    do live web research across a curated, catalyst-prone universe of ~35
    liquid US stocks/ETFs (not your personal watchlist) for recent news -
    earnings, product launches, partnerships, FDA decisions, analyst calls,
    macro events - and produces a short shortlist of what to consider buying
    at the next open, each with the catalyst it found and a plain-English
    plan. Runs automatically (no setup needed beyond the backend's
    `ANTHROPIC_API_KEY`); hidden if that key isn't configured.
11. **Settings** - configure and test the backend connection, broker
    credentials (Alpaca paper/live, Questrade), and check/enable notification
    permissions.

## AI features

The AI Insight card, AI Auto-Trader, and Tonight's Picks are powered by the
backend's `/api/ai/*` endpoints - see the
[backend README](../backend#ai-analysis) for how the ML model is trained, how
the optional AI analyst (`ANTHROPIC_API_KEY`) works, the auto-trader's safety
model (disabled by default, paper-trading by default, real-money trading
requires explicit confirmation, daily trade caps, position-size caps,
market-hours-only), and how the
[nightly Tonight's Picks scan](../backend#tonights-picks-nightly-deep-research-scan)
works.

⚠️ **The AI Auto-Trader can place real orders with real money in your Alpaca
account when configured to do so.** It is automated technical analysis +
machine learning, not financial advice, and is not guaranteed to be
profitable - you could lose money. You are solely responsible for any trades
it places, and can disable it at any time from the Auto Trade tab.

⚠️ **Tonight's Picks is speculative, AI-generated research, not financial
advice.** Recent news and "catalysts" do not guarantee a stock will move in
the expected direction at the next open - always do your own research before
acting on a pick.

## Background alerts

Watchlist price/signal alerts and position sell-alerts use **local
notifications**, checked two ways:

- **Live**: while the app is open, the WebSocket stream checks every update
  (~every 15s).
- **Background**: a `BGAppRefreshTask` periodically wakes the app to re-check
  alerts against the backend and post notifications, even when the app is
  closed.

This is *not* the same as push notifications (APNs) - iOS schedules
background refresh opportunistically based on usage, battery, and network
conditions, typically every 15 minutes to a few hours, so it's best-effort
rather than real-time. True push notifications would require a paid Apple
Developer account (for an APNs key) plus a server-side scheduler, which this
project doesn't include. For best results, make sure **Background App
Refresh** is enabled for Stock Chance in iOS Settings > General > Background
App Refresh.

Notification permission is requested the first time the app launches. The
**Settings** tab shows whether notifications are currently enabled and, if
denied, a button to jump to the system notification settings for Stock
Chance. `NotificationManager` registers itself as the
`UNUserNotificationCenterDelegate` so alerts show as a banner even while the
app is open, not just when it's in the background.
