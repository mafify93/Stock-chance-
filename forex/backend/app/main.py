from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import broker, daytrade, pairs, screener, signal

app = FastAPI(
    title="Forex Chance API",
    description=(
        "Technical-analysis signals (buy/sell/hold), a same-day intraday "
        "engine, a multi-pair screener and OANDA order execution for the "
        "Forex Chance iOS/macOS app. Market data and trading are both powered "
        "by the user's own OANDA account (fxPractice demo or fxTrade live)."
    ),
    version="0.1.0",
)

# Allow the iOS/macOS app (and local development tools) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pairs.router)
app.include_router(signal.router)
app.include_router(screener.router)
app.include_router(daytrade.router)
app.include_router(broker.router)


@app.get("/")
async def root():
    return {
        "name": "Forex Chance API",
        "status": "ok",
        "docs": "/docs",
        "disclaimer": (
            "Educational use only. Not financial advice. Leveraged forex "
            "trading carries a high risk of losing money rapidly."
        ),
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
