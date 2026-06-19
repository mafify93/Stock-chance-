#!/usr/bin/env python3
"""Run the auto-trader backtest locally against real OANDA history.

This charges the full spread on every trade, so the net result reflects what
you'd actually keep. Use it to check whether the strategy has a positive edge
*after* costs — and to see how trade frequency changes that edge — before
risking live money.

Usage
─────
    export OANDA_TOKEN="your-api-token"
    export OANDA_ACCOUNT_ID="your-account-id"

    # Default: practice candles, default pairs, 1.0-pip spread, $1000 NAV
    python -m scripts.backtest

    # Tune it
    python -m scripts.backtest --bars 3000 --spread 1.2 --nav 5000 \
        --pairs EUR_USD,GBP_USD --min-confidence 0.65 --no-session-filter

Run from the backend directory:  cd forex/backend && python -m scripts.backtest
"""
from __future__ import annotations

import argparse
import os
import sys

from app.autotrader.backtest import run_backtest
from app.autotrader.config import AutoTraderConfig
from app.providers import oanda
from app.providers.oanda import LIVE_BASE_URL, PRACTICE_BASE_URL


def _fmt_stats(label: str, s: dict) -> str:
    return (
        f"\n── {label} ──\n"
        f"  Trades:           {s['trades']}  ({s['wins']}W / {s['losses']}L, "
        f"win rate {s['win_rate']}%)\n"
        f"  Net P&L:          ${s['net_pnl_usd']:,.2f}  ({s['return_pct']:+.2f}%)\n"
        f"  Net pips total:   {s['net_pips']:+.1f}\n"
        f"  Spread paid:      {s['spread_paid_pips']:.1f} pips "
        f"(this is the cost of trading)\n"
        f"  EXPECTANCY:       {s['expectancy_pips']:+.2f} net pips / trade  "
        f"<-- the number that matters\n"
        f"  Avg win / loss:   {s['avg_win_pips']:+.1f} / {s['avg_loss_pips']:+.1f} pips\n"
        f"  Profit factor:    {s['profit_factor']}\n"
        f"  Max drawdown:     {s['max_drawdown_pct']:.2f}%\n"
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Auto-trader strategy backtester")
    p.add_argument("--pairs", default="", help="Comma-separated, e.g. EUR_USD,GBP_USD")
    p.add_argument("--bars", type=int, default=2000, help="M5 bars per pair (max 5000)")
    p.add_argument("--spread", type=float, default=1.0, help="Round-trip spread in pips")
    p.add_argument("--nav", type=float, default=1000.0, help="Starting account balance")
    p.add_argument("--env", default="practice", choices=["practice", "live"])
    p.add_argument("--risk-pct", type=float, default=None)
    p.add_argument("--rr-ratio", type=float, default=None)
    p.add_argument("--min-confidence", type=float, default=None)
    p.add_argument("--max-trades-per-day", type=int, default=None)
    p.add_argument("--no-session-filter", action="store_true",
                   help="Trade around the clock instead of London/NY only")
    args = p.parse_args()

    token = os.environ.get("OANDA_TOKEN")
    account_id = os.environ.get("OANDA_ACCOUNT_ID")
    if not token or not account_id:
        print("ERROR: set OANDA_TOKEN and OANDA_ACCOUNT_ID environment variables.",
              file=sys.stderr)
        return 1

    base_url = PRACTICE_BASE_URL if args.env == "practice" else LIVE_BASE_URL

    cfg = AutoTraderConfig()
    if args.risk_pct is not None:
        cfg.risk_pct = args.risk_pct
    if args.rr_ratio is not None:
        cfg.rr_ratio = args.rr_ratio
    if args.min_confidence is not None:
        cfg.min_confidence = args.min_confidence
    if args.max_trades_per_day is not None:
        cfg.max_trades_per_day = args.max_trades_per_day
    if args.no_session_filter:
        cfg.session_filter = False

    pairs = [s.strip() for s in args.pairs.split(",") if s.strip()] or cfg.pairs
    bars = max(100, min(args.bars, 5000))

    candles: dict = {}
    h1_candles: dict = {}
    for pair in pairs:
        try:
            df = oanda.get_candles(pair, token, "M5", bars, base_url)
            candles[pair] = df
            print(f"Loaded {len(df)} M5 bars for {pair}")
        except Exception as exc:
            print(f"  skip {pair} M5: {exc}", file=sys.stderr)
        try:
            df_h1 = oanda.get_candles(pair, token, "H1", 500, base_url)
            h1_candles[pair] = df_h1
            print(f"Loaded {len(df_h1)} H1 bars for {pair}")
        except Exception as exc:
            print(f"  skip {pair} H1: {exc}", file=sys.stderr)

    if not candles:
        print("ERROR: no candle data loaded.", file=sys.stderr)
        return 1

    spreads = {p: args.spread for p in candles}
    result = run_backtest(candles, cfg, spreads, args.nav,
                          h1_candles_by_pair=h1_candles or None)

    print("\n" + "=" * 64)
    print(f"BACKTEST  |  env={args.env}  spread={args.spread}pip  "
          f"session_filter={cfg.session_filter}  nav=${args.nav:,.0f}")
    print("=" * 64)
    print(_fmt_stats("OVERALL", result["overall"]))
    for s in result["per_pair"]:
        print(_fmt_stats(s["pair"], s))

    exp = result["overall"]["expectancy_pips"]
    print("=" * 64)
    if exp > 0:
        print(f"Net positive edge: +{exp} pips/trade after spread. "
              f"More trades would scale this up.")
    else:
        print(f"NEGATIVE edge: {exp} pips/trade after spread. "
              f"More trades would scale the LOSS up — not down.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
