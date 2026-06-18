# Forex Chance — Backend

A FastAPI service that turns a user's own [OANDA](https://www.oanda.com/) v20
account into a forex day-trading engine: technical-analysis signals, a
same-day intraday engine, a multi-pair screener, and order execution. OANDA
is both the **market-data feed** (candles, live pricing) and the **broker**
(account, positions, orders), so a single API token powers the whole app.

This mirrors the architecture of the Stock Chance backend, adapted for
currency pairs: prices are quoted in pips, the universe is the major/minor FX
pairs, and the "market clock" models the rolling 24/5 forex sessions
(Sydney → Tokyo → London → New York) instead of a single stock-exchange
session.

## Credentials — never stored server-side

The backend is **stateless about credentials**. The iOS app keeps the user's
OANDA API token and account ID in its Keychain and sends them on every request
as headers:

| Header             | Purpose                                            |
| ------------------ | -------------------------------------------------- |
| `Oanda-Api-Token`  | OANDA personal access token (`Authorization: Bearer`) |
| `Oanda-Account-Id` | OANDA account number, e.g. `101-001-1234567-001`   |
| `Oanda-Api-Env`    | `practice` (fxPractice demo, default) or `live` (fxTrade, **real money**) |

`practice` hits OANDA's demo environment (virtual money). `live` places
**real orders with real money** — the app gates that behind an explicit
acknowledgment and a per-order confirmation.

## Endpoints

| Method & path                     | What it does                                        |
| --------------------------------- | --------------------------------------------------- |
| `GET /api/pairs`                  | The tradable pair universe (majors + crosses)       |
| `GET /api/quote/{pair}`           | Live bid/ask/mid + spread (pips)                    |
| `GET /api/candles/{pair}`         | OHLCV candles (`granularity=M5\|H1\|H4\|D`)          |
| `GET /api/signal/{pair}`          | Swing buy/sell/hold signal with reasoning & levels  |
| `GET /api/screener`               | Scan many pairs → Buy / Sell / Hold buckets         |
| `GET /api/daytrade/session`       | The forex trading clock (active sessions, overlap)  |
| `GET /api/daytrade/signal/{pair}` | Same-day intraday signal (VWAP, ORB, EMA, RSI)      |
| `GET /api/daytrade/intraday/{pair}` | Intraday candles for charting                     |
| `GET /api/daytrade/top-pick`      | Ranked "what to trade right now" ideas              |
| `GET /api/broker/account`         | OANDA account summary (balance, NAV, margin)        |
| `GET /api/broker/positions`       | Open positions (long/short legs, unrealized P/L)    |
| `POST /api/broker/order`          | Place a market order (`units` ±, optional SL/TP)    |
| `POST /api/broker/close`          | Close a pair's long or short position               |

Interactive docs at `/docs`.

`pair` accepts `EUR_USD`, `EUR/USD`, or `eurusd` — all normalize to OANDA's
`EUR_USD` form.

## Run locally

```bash
cd forex/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then, e.g. (using a fxPractice token):

```bash
curl -H "Oanda-Api-Token: $OANDA_TOKEN" \
     -H "Oanda-Account-Id: $OANDA_ACCOUNT" \
     "http://127.0.0.1:8000/api/signal/EUR_USD"
```

## Tests

```bash
cd forex/backend && source .venv/bin/activate
pip install pytest
pytest
```

The suite covers pip math, the session clock, the signal engines, and OANDA
response parsing (HTTP layer mocked — no network or real credentials needed).

## Disclaimer

Educational use only. Not financial advice. Leveraged forex trading carries a
high risk of losing money rapidly.
