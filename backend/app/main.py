from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import daytrade, screener, signal, stocks, ws

app = FastAPI(
    title="Stock Chance API",
    description=(
        "Free, real-time-ish stock data, technical-analysis signals "
        "(buy/sell/hold) and screener for the Stock Chance iOS/macOS app. "
        "Powered by free public market data (Yahoo Finance)."
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

app.include_router(stocks.router)
app.include_router(signal.router)
app.include_router(screener.router)
app.include_router(daytrade.router)
app.include_router(ws.router)


@app.get("/")
async def root():
    return {
        "name": "Stock Chance API",
        "status": "ok",
        "docs": "/docs",
        "disclaimer": "Educational use only. Not financial advice.",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
