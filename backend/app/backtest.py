"""Walk-forward backtest of the signal engine (see `signals.analyze`)
against historical daily data.

IMPORTANT: This simulates how the app's own Buy/Sell/Hold rules *would have*
performed on past data. It does not model fees, slippage, taxes or
order-fill quality, and past performance is not a guarantee of future
results.
"""
from __future__ import annotations

import pandas as pd

from .signals import analyze

# Minimum number of trailing rows needed before the signal engine's
# indicators (SMA-200 etc.) become meaningful.
LOOKBACK = 200


def run_backtest(symbol: str, df: pd.DataFrame, initial_capital: float = 10000.0) -> dict:
    """Simulate buying on BUY/STRONG_BUY (while flat) and selling on
    SELL/STRONG_SELL (while holding), starting after `LOOKBACK` days of
    history. Returns a dict matching `models.BacktestResponse`.
    """
    if df is None or len(df) < LOOKBACK + 10:
        raise ValueError(
            f"Not enough history to backtest {symbol} (need at least {LOOKBACK + 10} daily bars)"
        )

    trades: list[dict] = []
    cash = initial_capital
    shares = 0.0
    entry_price: float | None = None
    entry_date = None

    for i in range(LOOKBACK, len(df)):
        window = df.iloc[: i + 1]
        try:
            result = analyze(symbol, window)
        except ValueError:
            continue

        price = result.price
        date = df.index[i]

        if shares == 0.0 and result.action in ("BUY", "STRONG_BUY"):
            shares = cash / price
            cash = 0.0
            entry_price = price
            entry_date = date
        elif shares > 0.0 and result.action in ("SELL", "STRONG_SELL"):
            cash = shares * price
            trades.append(_trade(entry_date, date, entry_price, price, shares, result.action))
            shares = 0.0
            entry_price = None
            entry_date = None

    last_price = float(df["Close"].iloc[-1])
    last_date = df.index[-1]
    if shares > 0.0 and entry_price is not None:
        cash = shares * last_price
        trades.append(_trade(entry_date, last_date, entry_price, last_price, shares, "END_OF_PERIOD"))
        shares = 0.0

    final_value = cash
    total_return_pct = (final_value - initial_capital) / initial_capital * 100

    start_price = float(df["Close"].iloc[LOOKBACK])
    buy_hold_return_pct = (last_price - start_price) / start_price * 100

    wins = sum(1 for t in trades if t["profit_loss"] > 0)
    win_rate_pct = (wins / len(trades) * 100) if trades else 0.0

    return {
        "symbol": symbol,
        "start_date": df.index[LOOKBACK].isoformat(),
        "end_date": last_date.isoformat(),
        "start_price": round(start_price, 2),
        "end_price": round(last_price, 2),
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return_pct, 2),
        "buy_hold_return_pct": round(buy_hold_return_pct, 2),
        "trade_count": len(trades),
        "win_count": wins,
        "win_rate_pct": round(win_rate_pct, 2),
        "trades": trades,
    }


def _trade(entry_date, exit_date, entry_price: float, exit_price: float, shares: float, exit_reason: str) -> dict:
    profit_loss = (exit_price - entry_price) * shares
    profit_loss_pct = (exit_price - entry_price) / entry_price * 100
    return {
        "entry_date": entry_date.isoformat(),
        "exit_date": exit_date.isoformat(),
        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),
        "profit_loss": round(profit_loss, 2),
        "profit_loss_pct": round(profit_loss_pct, 2),
        "exit_reason": exit_reason,
    }
