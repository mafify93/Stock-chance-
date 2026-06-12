# Stock Chance

A day-trading decision-support app: real-time(ish) quotes, technical-analysis
Buy/Sell/Hold signals with full reasoning, a "what to buy/what to sell"
screener, a same-day "Today" morning watchlist with suspected profit targets,
live "I bought this" position tracking with sell alerts, and free analyst
price targets - available for **any** stock, ETF, index, crypto or FX symbol
on Yahoo Finance, on **iOS and macOS**, with a dark "private trading terminal"
look.

## ⚠️ Read this first

No app can guarantee profitable trades or predict the market with certainty.
This project gives you transparent, data-driven **technical-analysis
signals** (RSI, MACD, moving averages, Bollinger Bands, Stochastic, ADX,
ATR) plus free analyst price targets - combined into a single Buy/Sell/Hold
recommendation with a confidence score and a plain-English explanation of
*why*. Use it as a decision-support tool, not as financial advice. Trading
is risky.

## Project layout

- [`backend/`](backend) - Python/FastAPI service: free market data (Yahoo
  Finance, no API key needed), the signal engine, screener, and a WebSocket
  for live updates. See [backend/README.md](backend/README.md).
- [`app/`](app) - SwiftUI multiplatform app for iOS and macOS. See
  [app/README.md](app/README.md).

## Quick start

```bash
# 1. Run the backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 2. Generate and open the Xcode project (on a Mac)
cd ../app
brew install xcodegen   # one-time
xcodegen generate
open StockChance.xcodeproj
```

Run the **StockChance (macOS)** scheme to try it on Mac, or
**StockChance (iOS)** for the simulator/iPhone. The app talks to
`http://127.0.0.1:8000` by default - change this in the app's Settings tab
if you deploy the backend elsewhere.

## How the signals work

For each symbol, the backend pulls ~1 year of daily price/volume history and
computes:

- **Trend**: price vs 50/200-day moving averages, golden/death cross
- **Momentum**: RSI, MACD line vs signal line (incl. fresh crossovers)
- **Volatility / mean reversion**: Bollinger Bands, Stochastic Oscillator
- **Volume confirmation**: volume vs its 20-day average
- **Trend strength**: ADX (amplifies or dampens the above)

Each indicator casts a weighted vote from -1 (bearish) to +1 (bullish). The
weighted average becomes a score from -1 to +1, mapped to **Strong
Sell / Sell / Hold / Buy / Strong Buy** with a confidence percentage and a
list of the specific reasons behind the call. ATR is used to suggest
entry/stop-loss/take-profit levels with a 1:2 risk/reward ratio.

Free Yahoo Finance analyst recommendations and price targets are shown
alongside the technical signal where available.

## Same-day ("Today") trading

For traders who want to buy and sell within the same session:

- **Today tab** - before/after the open, see the current US market session
  (pre-market / open / after-hours / closed with a countdown) plus
  **Buy at Open**, **Watch for a Dip**, and **Avoid Today** lists, each with a
  plain-English plan and an ATR-based "suspected profit" estimate.
- **Day Trade Signal** (on each stock's detail screen) - a same-day
  Buy/Sell/Hold call from intraday (5-minute) price action: VWAP position,
  opening-range breakout, EMA9/EMA20 momentum, intraday RSI dips/peaks, and
  relative volume spikes - with suggested entry/target/stop levels and an
  intraday chart.
- **Real-time alerts** - `TAKE_PROFIT_ZONE`, `STOP_LOSS_ZONE`, and `EOD_EXIT`
  (sell before the close) flags update live via WebSocket.

## "I bought this" position tracking

From any stock's detail screen, tap **I Bought This** and enter your entry
price and quantity. The **Positions** tab then tracks it with a live current
price, unrealized P/L, and the same-day signal - and sends a local
notification the moment the same-day signal or alert says it's time to sell.

## What's next

This is the foundation - good places to extend:

- Add more free data providers (Finnhub, Alpha Vantage, Twelve Data, Stooq)
  as additional signal inputs (see `backend/README.md`).
- News/sentiment scoring.
- Backtesting the signal engine against historical data.
- Push notifications when a watchlist symbol's signal changes.
- Portfolio tracking / paper trading.
