"""Telegram notification sender for the auto-trader bot.

Configure via environment variables:
    TELEGRAM_BOT_TOKEN  — your @BotFather token
    TELEGRAM_CHAT_ID    — your personal or group chat ID

Both must be set for notifications to fire; missing either silently disables them.
"""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger(__name__)

_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def _enabled() -> bool:
    return bool(_BOT_TOKEN and _CHAT_ID)


def send(message: str) -> None:
    """Fire-and-forget Telegram message — logs and swallows all errors."""
    if not _enabled():
        return
    try:
        url = f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage"
        with httpx.Client(timeout=5) as client:
            client.post(url, json={"chat_id": _CHAT_ID, "text": message, "parse_mode": "HTML"})
    except Exception as exc:
        log.debug(f"Telegram send failed (non-fatal): {exc}")


def notify_halt(reason: str) -> None:
    send(f"\U0001f6d1 <b>AutoTrader HALTED</b>\n{reason}")


def notify_trade_entry(
    pair: str,
    side: str,
    units: int,
    entry: float,
    stop: float,
    target: float,
    signal_type: str,
    confidence: float,
) -> None:
    emoji = "\U0001f7e2" if side == "long" else "\U0001f534"
    display = pair.replace("_", "/")
    send(
        f"{emoji} <b>Trade Entry</b> — {display}\n"
        f"Side: {side.upper()} · {units:,} units\n"
        f"Entry: {entry:.5f} | SL: {stop:.5f} | TP: {target:.5f}\n"
        f"Signal: {signal_type} · Confidence: {confidence:.0f}%"
    )


def notify_trade_close(pair: str, side: str, realized_pl: float) -> None:
    if realized_pl > 0:
        emoji, outcome = "✅", "WIN"
    elif realized_pl < 0:
        emoji, outcome = "❌", "LOSS"
    else:
        emoji, outcome = "➖", "SCRATCH"
    display = pair.replace("_", "/")
    send(
        f"{emoji} <b>Trade Closed</b> — {display}\n"
        f"Side: {side.upper()} · {outcome}\n"
        f"P&L: {realized_pl:+.2f}"
    )


def notify_daily_summary(daily_pl: float, trades_today: int, start_balance: float) -> None:
    pct = (daily_pl / start_balance * 100) if start_balance > 0 else 0.0
    emoji = "\U0001f4c8" if daily_pl >= 0 else "\U0001f4c9"
    send(
        f"{emoji} <b>Daily Summary</b>\n"
        f"P&L: {daily_pl:+.2f} ({pct:+.2f}%)\n"
        f"Trades: {trades_today}"
    )
