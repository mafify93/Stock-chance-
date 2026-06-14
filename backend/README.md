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
- **Same-day ("day trading") signals** - market session status, an intraday
  (5-minute) Buy/Sell/Hold signal with VWAP, opening-range, momentum, RSI and
  volume-based reasoning plus suggested entry/target/stop and take-profit /
  stop-loss / end-of-day-exit alerts, a morning "what to buy at the open" scan,
  and a live WebSocket (`/ws/daytrade`).
- **AI analysis** - a machine-learning model trained on years of price
  history that estimates the probability a stock is higher in 5 trading days,
  plus (optionally) an LLM "AI analyst" summary, combined with the rule-based
  signal into one `/api/ai/analysis/{symbol}` recommendation.
- **AI Auto-Trader** - an optional background loop that re-uses the same
  combined AI recommendation to automatically place orders through Alpaca,
  with confidence thresholds, position-size limits, a daily trade cap, and a
  hard "paper vs. live + explicit confirmation" gate before any real money
  moves.

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
| `GET /api/daytrade/session` | Current US market session (pre-market/open/after-hours/closed) |
| `GET /api/daytrade/signal/AAPL` | Same-day Buy/Sell/Hold signal from intraday price action |
| `GET /api/daytrade/intraday/AAPL?period=1d&interval=5m` | Intraday OHLCV candles for charting |
| `GET /api/daytrade/morning?top=8` | Morning scan: Buy at Open / Watch / Avoid candidates |
| `WS /ws/daytrade?symbols=AAPL,MSFT` | Live same-day signal + alert stream (~20s) |
| `GET /api/ai/analysis/AAPL` | Combined signal + ML prediction + AI analyst recommendation |
| `GET /api/ai/auto-trader/config` | Current auto-trader configuration |
| `POST /api/ai/auto-trader/config` | Update auto-trader configuration |
| `GET /api/ai/auto-trader/status` | Auto-trader status + recent decisions |
| `POST /api/ai/auto-trader/run-now` | Trigger one auto-trader evaluation immediately |

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

## AI analysis

`GET /api/ai/analysis/{symbol}` combines three independent opinions into one
`combined_action` / `combined_confidence`:

1. **Rule-based signal** - the same technical-analysis engine as
   `/api/signal` (RSI, MACD, moving averages, Bollinger Bands, Stochastic,
   ADX, ATR).
2. **ML model** (`app/ml/`) - a `HistGradientBoostingClassifier` trained on
   ~5 years of daily data across ~90 stocks/ETFs, predicting the probability
   the price is higher in 5 trading days from a set of scale-independent
   technical features. A pre-trained model is committed at
   `app/ml/model.joblib` (test accuracy ~52%, vs. a ~50-55% naive baseline -
   it provides a small statistical edge, not a crystal ball). Retrain it with:

   ```bash
   cd backend
   python3 -m scripts.train_ml_model
   ```

3. **AI analyst** (`app/ai_analyst.py`) - optional. If the `ANTHROPIC_API_KEY`
   environment variable is set, the backend sends the symbol, current
   signal, and ML prediction to the Claude API and asks for a JSON
   `{"action", "confidence", "summary"}` opinion in plain English. Set
   `ANTHROPIC_MODEL` to override the default model. If the key is absent or
   the request fails for any reason, this is simply omitted (`llm: null`,
   `llm_configured: false`) - everything else still works.

`app/ai_combine.py` merges all three (equally weighted by direction and
confidence) into `combined_action` / `combined_confidence`. This same combine
logic is what the AI Auto-Trader acts on, so the recommendation you see in the
app and the trades the auto-trader makes can never disagree.

## AI Auto-Trader

`app/auto_trader.py` runs a background loop (started in `main.py`'s FastAPI
lifespan) that, for each configured symbol, computes the combined AI
recommendation above and can place a real order through Alpaca.

**Safety model (all defaults are the safe choice):**

- `enabled: false` by default - the loop does nothing until you opt in.
- `environment: "paper"` by default. Even with `enabled: true`, placing a
  **live** order additionally requires `confirmed_real_money: true`. If
  `environment: "live"` but `confirmed_real_money: false`, decisions are
  logged as `"DRY RUN"` and nothing is sent to Alpaca.
- `min_confidence` (default 70%) - only acts when the combined confidence
  meets this bar; otherwise it's logged as a HOLD/skip with a reason.
- `max_position_value` (default $100) caps the dollar amount of any single
  BUY order. The auto-trader never adds to an existing position (no
  pyramiding).
- `max_daily_trades` (default 3) caps executed orders per UTC day.
- Only evaluates while the US market is open
  (`GET /api/daytrade/session`).
- Every decision - HOLD, skipped, or executed, with a human-readable reason -
  is logged to `backend/data/auto_trader_log.json` and surfaced via
  `GET /api/ai/auto-trader/status`.

**⚠️ Credential storage deviation:** unlike the rest of this API (which never
stores brokerage credentials and expects them per-request from the app), the
auto-trader **must** persist your Alpaca API keys server-side
(`backend/data/auto_trader_config.json`, file permissions `0600`) so it can
keep trading while the app is closed. That entire directory is gitignored.
Only run this backend on a machine you trust, and validate with Alpaca
**paper** credentials before ever switching `environment` to `"live"` and
confirming real-money trading.

Configure it via `POST /api/ai/auto-trader/config` (or the "AI Auto-Trader"
screen in Settings in the app), and use `POST /api/ai/auto-trader/run-now` to
trigger one evaluation immediately for testing.

## Deploying

For the iOS/macOS app to reach this API from a real device, deploy it
somewhere reachable (Fly.io, Render, Railway, a VPS, etc.) and point the app
at that URL in Settings. A simple production start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
