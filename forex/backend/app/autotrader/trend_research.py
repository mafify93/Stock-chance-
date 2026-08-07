"""Higher-timeframe trend-following research harness.

This is deliberately SEPARATE from the live intraday engine and the M5
backtester. Its purpose is to test the one class of FX edge with real,
published out-of-sample evidence — time-series trend-following — on enough
history to actually mean something. On H4 candles OANDA's 5,000-bar request
limit is ~2.5 years; on Daily ~14 years, versus the ~3.5 weeks an M5 window
buys. That data depth is the whole point.

Strategy: classic Donchian-channel breakout (Turtle-style).
  - Enter LONG when price breaks above the highest high of the last
    `entry_n` bars; SHORT below the lowest low. Optional long-SMA trend
    filter (only trade in the direction of the higher-timeframe trend).
  - Stop: `stop_atr` × ATR(atr_n) from entry.
  - Exit: opposite `exit_n`-bar channel (Turtle exit) or the stop, whichever
    comes first.
  - One position at a time. Round-trip spread charged on entry+exit.

Everything is evaluated in R-multiples (P&L per unit of risk) so the result
is instrument-agnostic, plus a compounded fixed-fractional equity curve for
drawdown/Calmar. Crucially it reports CONCENTRATION — the share of net P&L
from the best 3 trades — because a trend edge carried by two lucky moves is
noise, not an edge, and that is the exact trap that has fooled us before.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .. import pips
from ..indicators import average_true_range


@dataclass
class TrendParams:
    entry_n: int = 20          # breakout lookback (bars)
    exit_n: int = 10           # opposite-channel exit lookback
    atr_n: int = 14            # ATR period for the stop
    stop_atr: float = 2.0      # stop distance = stop_atr * ATR
    ma_n: int = 100            # long-trend SMA filter; 0 disables it
    risk_frac: float = 0.01    # fraction of equity risked per trade
    spread_pips: float = 2.0   # round-trip spread cost, in pips
    start_equity: float = 100_000.0


def _stats(trades: list[dict], equity_curve: list[float], start_equity: float) -> dict:
    """Summarise a list of closed trades (each with 'pnl_r' and 'pnl_cash')."""
    n = len(trades)
    if n == 0:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "expectancy_r": 0.0, "avg_win_r": 0.0, "avg_loss_r": 0.0,
            "profit_factor": None, "return_pct": 0.0, "max_drawdown_pct": 0.0,
            "calmar_ratio": None, "top3_pct_of_net": None,
            "end_equity": round(start_equity, 2),
        }
    wins = [t for t in trades if t["pnl_cash"] > 0]
    losses = [t for t in trades if t["pnl_cash"] < 0]
    gross_win = sum(t["pnl_cash"] for t in wins)
    gross_loss = -sum(t["pnl_cash"] for t in losses)
    net = sum(t["pnl_cash"] for t in trades)
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    # Max drawdown on the compounded equity curve.
    peak = equity_curve[0] if equity_curve else start_equity
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)

    end_equity = equity_curve[-1] if equity_curve else start_equity
    ret_pct = (end_equity - start_equity) / start_equity * 100
    calmar = (ret_pct / 100) / max_dd if max_dd > 0 else float("inf")

    # Concentration: share of NET profit from the best 3 trades. A robust
    # edge is spread across many trades; a fragile one is 2-3 lucky moves.
    top3 = sorted((t["pnl_cash"] for t in trades), reverse=True)[:3]
    concentration = (sum(top3) / net) if net > 0 else None

    exp_r = sum(t["pnl_r"] for t in trades) / n
    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(100 * len(wins) / n, 1),
        "expectancy_r": round(exp_r, 3),
        "avg_win_r": round(sum(t["pnl_r"] for t in wins) / len(wins), 2) if wins else 0.0,
        "avg_loss_r": round(sum(t["pnl_r"] for t in losses) / len(losses), 2) if losses else 0.0,
        "profit_factor": round(pf, 2) if pf != float("inf") else None,
        "return_pct": round(ret_pct, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "calmar_ratio": round(calmar, 2) if calmar != float("inf") else None,
        "top3_pct_of_net": round(100 * concentration, 1) if concentration is not None else None,
        "end_equity": round(end_equity, 2),
    }


def simulate_trend(df: pd.DataFrame, pair: str, p: TrendParams) -> dict:
    """Run the Donchian trend-follower over `df` (OHLCV, time-indexed).

    Returns overall stats, the trade list, and equity curve.
    """
    if len(df) < max(p.entry_n, p.exit_n, p.atr_n, p.ma_n) + 5:
        return {"trades": 0, "error": "not enough bars"}

    highs = df["High"].values
    lows = df["Low"].values
    closes = df["Close"].values
    times = df.index
    atr = average_true_range(df, p.atr_n).values
    sma = df["Close"].rolling(p.ma_n).mean().values if p.ma_n > 0 else None

    spread_price = p.spread_pips * pips.pip_size(pair)
    warmup = max(p.entry_n, p.atr_n, p.ma_n) + 1

    equity = p.start_equity
    equity_curve: list[float] = [equity]
    trades: list[dict] = []

    pos = 0          # +1 long, -1 short, 0 flat
    entry_px = stop_px = 0.0
    risk_cash = 0.0
    entry_time = None

    for i in range(warmup, len(df)):
        a = atr[i]
        if a is None or a != a or a <= 0:  # NaN guard
            equity_curve.append(equity)
            continue

        if pos == 0:
            prior_high = highs[i - p.entry_n:i].max()
            prior_low = lows[i - p.entry_n:i].min()
            up_trend = (sma is None) or (sma[i] == sma[i] and closes[i] > sma[i])
            dn_trend = (sma is None) or (sma[i] == sma[i] and closes[i] < sma[i])

            if highs[i] > prior_high and up_trend:
                pos = 1
                entry_px = closes[i] + spread_price / 2
                stop_px = entry_px - p.stop_atr * a
                risk_cash = p.risk_frac * equity
                entry_time = times[i]
            elif lows[i] < prior_low and dn_trend:
                pos = -1
                entry_px = closes[i] - spread_price / 2
                stop_px = entry_px + p.stop_atr * a
                risk_cash = p.risk_frac * equity
                entry_time = times[i]
            equity_curve.append(equity)
            continue

        # In a position — check stop first (intrabar), then channel exit on close.
        exit_px = None
        risk_dist = abs(entry_px - stop_px)
        if pos == 1:
            if lows[i] <= stop_px:
                exit_px = stop_px - spread_price / 2
            elif closes[i] < lows[i - p.exit_n:i].min():
                exit_px = closes[i] - spread_price / 2
        else:
            if highs[i] >= stop_px:
                exit_px = stop_px + spread_price / 2
            elif closes[i] > highs[i - p.exit_n:i].max():
                exit_px = closes[i] + spread_price / 2

        if exit_px is not None:
            move = (exit_px - entry_px) if pos == 1 else (entry_px - exit_px)
            pnl_r = move / risk_dist if risk_dist > 0 else 0.0
            pnl_cash = pnl_r * risk_cash
            equity += pnl_cash
            trades.append({
                "pair": pair,
                "side": "long" if pos == 1 else "short",
                "entry_time": str(entry_time)[:16],
                "exit_time": str(times[i])[:16],
                "pnl_r": round(pnl_r, 3),
                "pnl_cash": round(pnl_cash, 2),
            })
            pos = 0
        equity_curve.append(equity)

    result = _stats(trades, equity_curve, p.start_equity)
    result["trades_list"] = trades
    return result


def run_trend_research(df: pd.DataFrame, pair: str, p: TrendParams,
                       walk_forward_pct: float = 0.3) -> dict:
    """Full-period result plus an out-of-sample walk-forward on the last
    `walk_forward_pct` of bars (trained-on-nothing; the strategy has no fit,
    so OOS here means 'did the same rules keep working on unseen recent data')."""
    full = simulate_trend(df, pair, p)
    out = {"pair": pair, "bars": len(df), "full": full}

    if 0 < walk_forward_pct < 1 and len(df) > 200:
        split = int(len(df) * (1 - walk_forward_pct))
        oos_df = df.iloc[split:]
        out["walk_forward"] = simulate_trend(oos_df, pair, p)
    return out
