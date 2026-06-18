# Forex Chance

A forex day-trading app — a FastAPI backend and a SwiftUI iOS/macOS frontend —
built on the same architecture as **Stock Chance**, but rebuilt for currency
pairs and using **OANDA** as both the market-data feed and the broker.

```
forex/
├── backend/   FastAPI service: signals, screener, intraday engine, OANDA execution
├── app/       SwiftUI iOS/macOS app
└── render.yaml  One-click backend deploy to Render
```

## How it differs from Stock Chance

| Stock Chance                          | Forex Chance                                  |
| ------------------------------------- | --------------------------------------------- |
| Yahoo Finance data + Alpaca/Questrade | OANDA for **both** data and trading           |
| US stocks/ETFs (hundreds of tickers)  | Major + cross **currency pairs**              |
| Prices/targets in dollars             | Prices/targets in **pips**                    |
| One 9:30–16:00 ET session             | Rolling **24/5** Sydney→Tokyo→London→New York |
| Real traded volume                    | OANDA **tick volume** proxy                   |
| Shares, market/limit orders           | **Units** (long +, short −), lots, FOK market |

The signal engines (trend + momentum + volatility indicators, a same-day
intraday engine, and a combined "Top Pick" ranker) carry over directly —
they're indicator math that applies equally to any OHLCV series.

## Quick start

**Backend**
```bash
cd forex/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
```

**App**
```bash
cd forex/app
xcodegen generate && open ForexChance.xcodeproj
```

Add a free OANDA **fxPractice** token + account ID in the app's
**Settings → Broker**, point it at your backend, and you're trading on demo
money. See `backend/README.md` and `app/README.md` for details.

## Disclaimer

Educational use only. Not financial advice. Leveraged forex trading carries a
high risk of losing money rapidly — only the user's own OANDA account places
any orders, and live trading requires explicit, per-order confirmation.
