# Forex Chance — iOS / macOS app

A SwiftUI app for forex day trading, powered by the Forex Chance backend and
the user's own OANDA account. It mirrors the structure of the Stock Chance
app, rebuilt around currency pairs: prices in pips, the 24/5 forex session
clock, and OANDA order execution.

## Tabs

- **Today** — the forex trading clock (which sessions are live, whether the
  London/New York overlap is on) plus ranked "Top Pick" trade ideas.
- **Markets** — browse/search the major and cross pairs; tap for detail.
- **Screener** — scan the universe into Buy / Sell / Hold buckets.
- **Positions** — OANDA account summary and open positions, with one-tap
  close. Switch between practice (demo) and live accounts.
- **Settings** — backend URL and OANDA credentials.

The **pair detail** screen shows a live quote/spread, a 5-minute chart with
VWAP, the same-day intraday signal, the H1 trend signal with full reasoning,
and a **Trade** button that opens the order ticket (side, units/lots, with a
real-money confirmation for live orders).

## Credentials

OANDA API tokens and account IDs are stored only in the device **Keychain**
and sent with each request — never persisted by the backend. The practice
(fxPractice) environment uses virtual money and is safe to use freely; the
live (fxTrade) environment places real orders and is gated behind an explicit
acknowledgment plus a per-order confirmation.

Create a token at OANDA → **Manage API Access**, and find your account ID
(e.g. `101-001-1234567-001`) in the OANDA account portal.

## Build

The project is generated with [XcodeGen](https://github.com/yonyz/XcodeGen):

```bash
cd forex/app
xcodegen generate
open ForexChance.xcodeproj
```

Targets iOS 16+ / macOS 13+ (uses Swift Charts and async/await). CI builds an
unsigned IPA on every push — see `.github/workflows/build-forex-ios.yml`.

Point the app at your backend in **Settings → Backend** (defaults to
`http://127.0.0.1:8000` for local development).

## Disclaimer

Educational technical analysis, not financial advice. Leveraged forex trading
carries a high risk of losing money rapidly.
