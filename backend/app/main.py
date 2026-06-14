from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auto_trader import auto_trader
from .routers import ai, auto_trader as auto_trader_router, backtest, broker, daytrade, screener, signal, stocks, ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    auto_trader.start()
    try:
        yield
    finally:
        auto_trader.stop()


app = FastAPI(
    title="Stock Chance API",
    description=(
        "Free, real-time-ish stock data, technical-analysis signals "
        "(buy/sell/hold) and screener for the Stock Chance iOS/macOS app. "
        "Powered by free public market data (Yahoo Finance)."
    ),
    version="0.1.0",
    lifespan=lifespan,
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
app.include_router(broker.router)
app.include_router(backtest.router)
app.include_router(ai.router)
app.include_router(auto_trader_router.router)
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
