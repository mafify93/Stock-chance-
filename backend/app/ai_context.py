"""Shared helpers for building "live data" context blocks for the AI-powered
features that talk to Claude about the user's actual data - "Ask the AI"
chat (`app.ai_chat`) and the Daily AI Briefing (`app.daily_briefing`).

Both features need the same two things: a quick signal/ML snapshot for a
handful of symbols, and a summary of the AI auto-trader's recent activity.
Keeping that logic here avoids duplicating it (and its Render-free-tier cost
considerations) between the two modules.
"""
from __future__ import annotations

from .auto_trader import auto_trader
from .ml.model import ml_predictor
from .providers import yahoo
from .signals import analyze

# Cap how many symbols get a full signal snapshot per request - each one is a
# Yahoo history fetch + indicator pass, which adds up on Render's free tier.
MAX_CONTEXT_SYMBOLS = 12


def symbol_snapshot(symbol: str) -> dict | None:
    """Current price, rule-based signal, and ML prediction for `symbol`, or
    `None` if its data can't be loaded (e.g. an invalid/delisted ticker)."""
    try:
        df = yahoo.get_history(symbol, "6mo", "1d")
        result = analyze(symbol, df)
    except Exception:  # noqa: BLE001 - best-effort context, skip bad symbols
        return None
    ml_result = ml_predictor.predict(df)
    return {
        "symbol": symbol,
        "price": result.price,
        "signal": result.action,
        "confidence": round(result.confidence, 1),
        "reasons": result.reasons[:3],
        "ml_probability_up": ml_result["probability_up"] if ml_result else None,
    }


def auto_trader_summary(decision_limit: int = 5) -> dict:
    """A compact summary of the auto-trader's configuration and most recent
    decisions, suitable for embedding in an AI prompt."""
    status = auto_trader.get_status()
    return {
        "enabled": status.config.enabled,
        "broker": status.config.broker,
        "auto_select": status.config.auto_select,
        "confirmed_real_money": status.config.confirmed_real_money,
        "trades_today": status.trades_today,
        "max_daily_trades": status.config.max_daily_trades,
        "recent_decisions": [
            {
                "timestamp": d.timestamp,
                "symbol": d.symbol,
                "action": d.action,
                "confidence": d.combined_confidence,
                "executed": d.executed,
                "reason": d.reason,
            }
            for d in status.decisions[:decision_limit]
        ],
    }


def dedupe_symbols(*symbol_lists: list[str], limit: int = MAX_CONTEXT_SYMBOLS) -> list[str]:
    """Uppercases and de-duplicates symbols across one or more lists,
    preserving order and stopping once `limit` is reached."""
    seen: list[str] = []
    for symbols in symbol_lists:
        for sym in symbols:
            upper = sym.upper()
            if upper not in seen:
                seen.append(upper)
            if len(seen) >= limit:
                return seen
    return seen
