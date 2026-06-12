from __future__ import annotations

from pydantic import BaseModel


class SearchResult(BaseModel):
    symbol: str
    name: str | None = None
    exchange: str | None = None
    type: str | None = None
    sector: str | None = None


class Quote(BaseModel):
    symbol: str
    price: float
    previous_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    open: float | None = None
    volume: float | None = None
    market_cap: float | None = None
    currency: str | None = None
    exchange: str | None = None
    fifty_day_average: float | None = None
    two_hundred_day_average: float | None = None
    year_high: float | None = None
    year_low: float | None = None


class Candle(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class AnalystOutlook(BaseModel):
    recommendation_key: str | None = None
    target_mean_price: float | None = None
    target_high_price: float | None = None
    target_low_price: float | None = None
    number_of_analyst_opinions: int | None = None
    recommendations_summary: dict | None = None


class SignalResponse(BaseModel):
    symbol: str
    action: str
    score: float
    confidence: float
    price: float
    reasons: list[str]
    indicators: dict
    levels: dict
    analyst: AnalystOutlook | None = None
    disclaimer: str = (
        "Educational technical-analysis output, not financial advice. "
        "Past performance and indicator patterns do not guarantee future results."
    )


class ScreenerItem(BaseModel):
    symbol: str
    action: str
    score: float
    confidence: float
    price: float
    change_percent: float | None = None


class ScreenerResponse(BaseModel):
    generated_at: str
    buy: list[ScreenerItem]
    sell: list[ScreenerItem]
    hold: list[ScreenerItem]
    errors: dict[str, str] = {}
