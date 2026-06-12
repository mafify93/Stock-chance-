# Stock Chance API (backend)

A free, no-API-key-required backend that powers the Stock Chance iOS/macOS
app. It provides:

- **Search** any stock, ETF, index, crypto or FX symbol (Yahoo Finance).
- **Quotes** - near real-time price snapshots.
- **History** - OHLCV candles for charting.
- **Signals** - a composite Buy / Sell / Hold technical-analysis engine with
  human-readable reasoning, confidence score, and suggested entry / stop-loss
  / take-profit levels (ATR-based).
- **Screener** - "what to buy / what to sell right now" across a curated
  universe of popular US stocks/ETFs or your own watchlist.
- **Live updates** - a WebSocket (`/ws/watch`) that streams quote + signal
  updates every ~15 seconds for a list of symbols.
- **Analyst outlook** - free analyst price targets / recommendation
  consensus bundled with Yahoo Finance data, where available.

## ⚠️ Important disclaimer

The "signals" are **rule-based technical analysis**, computed from public
price/volume history (RSI, MACD, moving averages, Bollinger Bands,
Stochastic Oscillator, ADX, ATR). They are a decision-support tool, **not a
guarantee of future price movement and not financial advice**. No algorithm
can reliably predict short-term stock prices. Always do your own research
and never risk money you can't afford to lose.

## Running locally

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://127.0.0.1:8000`, with interactive docs
at `http://127.0.0.1:8000/docs`.

## Running tests

```bash
pip install pytest
python3 -m pytest
```

## Key endpoints

| Endpoint | Description |
| --- | --- |
| `GET /api/search?q=apple` | Search any symbol |
| `GET /api/quote/AAPL` | Near real-time quote |
| `GET /api/history/AAPL?period=6mo&interval=1d` | OHLCV candles |
| `GET /api/signal/AAPL` | Buy/Sell/Hold signal + reasoning + levels |
| `GET /api/screener?top=10` | Top buy/sell/hold across the default universe |
| `GET /api/screener?symbols=AAPL,MSFT&top=10` | Screener over a custom list |
| `WS /ws/watch?symbols=AAPL,MSFT` | Live quote + signal stream |

## Data sources

Out of the box this uses **Yahoo Finance** via `yfinance` + Yahoo's public
search/quote endpoints - it's free, requires no API key/signup, and covers
essentially any publicly traded symbol worldwide (stocks, ETFs, indices,
crypto, FX). Yahoo's analyst recommendation/price-target data (also free) is
included in `/api/signal` when available.

This is an **unofficial** API, so it can occasionally rate-limit or change
shape. Responses are cached briefly (`app/cache.py`) to reduce load.

### Adding more free providers

The provider layer (`app/providers/`) is intentionally pluggable. Good
free-tier (signup required for an API key) options to add later:

- **Finnhub** - free tier includes analyst recommendation trends, price
  targets, earnings, and basic news/sentiment.
- **Alpha Vantage** - free tier includes technical indicators and
  fundamental data (rate-limited to ~25 requests/day).
- **Twelve Data** - free tier with real-time and historical data for stocks,
  forex and crypto.
- **Stooq** (`https://stooq.com`) - free CSV historical data, no key needed,
  useful as a fallback if Yahoo rate-limits.

To add one, create `app/providers/<name>.py` following the same pattern as
`yahoo.py`, then wire it into the routers/signal engine as an additional
input (e.g. extra votes in `app/signals.py`, or an additional field in
`/api/signal`).

## Deploying

For the iOS/macOS app to reach this API from a real device, deploy it
somewhere reachable (Fly.io, Render, Railway, a VPS, etc.) and point the app
at that URL in Settings. A simple production start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
