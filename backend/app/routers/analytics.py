"""Analytics dashboard router — aggregates auto-trader history into
performance metrics."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter

from ..auto_trader import auto_trader
from ..models import AnalyticsResponse, DailyPerf

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/performance", response_model=AnalyticsResponse)
async def get_performance() -> AnalyticsResponse:
    """Compute performance metrics from the auto-trader decision log."""
    with auto_trader._lock:
        log = list(auto_trader._log)

    # Only consider executed decisions
    executed = [e for e in log if e.get("executed")]

    total_trades = len(executed)
    buys = sum(1 for e in executed if e.get("action") in ("BUY", "STRONG_BUY"))
    sells = sum(1 for e in executed if e.get("action") in ("SELL", "STRONG_SELL"))

    # Match SELLs to their preceding BUY to compute P&L
    # Build a per-symbol queue of BUY entry_prices
    pending_buys: dict[str, list[float]] = defaultdict(list)
    pnls: list[float] = []
    daily: dict[str, dict] = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "wins": 0, "losses": 0})

    for entry in log:
        if not entry.get("executed"):
            continue

        action = entry.get("action", "")
        symbol = entry.get("symbol", "")
        ts = entry.get("timestamp", "")
        date_str = ts[:10] if len(ts) >= 10 else "unknown"
        entry_price = entry.get("entry_price")

        daily[date_str]["trades"] += 1

        if action in ("BUY", "STRONG_BUY"):
            if entry_price is not None:
                pending_buys[symbol].append(float(entry_price))
        elif action in ("SELL", "STRONG_SELL"):
            sell_price = entry.get("entry_price")
            if sell_price is not None and pending_buys.get(symbol):
                buy_price = pending_buys[symbol].pop(0)
                # entry_price on a SELL = the sell price
                pnl = (float(sell_price) - buy_price) * entry.get("qty", 1)
                pnls.append(pnl)
                daily[date_str]["pnl"] += pnl
                if pnl >= 0:
                    daily[date_str]["wins"] += 1
                else:
                    daily[date_str]["losses"] += 1

    wins = sum(1 for p in pnls if p >= 0)
    losses = sum(1 for p in pnls if p < 0)
    total_pnl = sum(pnls)
    win_pnls = [p for p in pnls if p >= 0]
    loss_pnls = [p for p in pnls if p < 0]

    win_rate = (wins / len(pnls) * 100) if pnls else 0.0
    avg_win = (sum(win_pnls) / len(win_pnls)) if win_pnls else 0.0
    avg_loss = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0.0
    largest_win = max(win_pnls, default=0.0)
    largest_loss = min(loss_pnls, default=0.0)

    # Period days: from first log entry to now
    if log:
        first_ts = log[0].get("timestamp", "")
        try:
            first_dt = datetime.fromisoformat(first_ts)
            period_days = max(1, (datetime.now(timezone.utc) - first_dt).days)
        except Exception:  # noqa: BLE001
            period_days = 0
    else:
        period_days = 0

    daily_list = sorted(
        [
            DailyPerf(
                date=date,
                trades=v["trades"],
                pnl=round(v["pnl"], 2),
                wins=v["wins"],
                losses=v["losses"],
            )
            for date, v in daily.items()
        ],
        key=lambda d: d.date,
    )

    return AnalyticsResponse(
        total_trades=total_trades,
        buys=buys,
        sells=sells,
        wins=wins,
        losses=losses,
        win_rate=round(win_rate, 1),
        total_pnl=round(total_pnl, 2),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        largest_win=round(largest_win, 2),
        largest_loss=round(largest_loss, 2),
        daily=daily_list,
        period_days=period_days,
    )
