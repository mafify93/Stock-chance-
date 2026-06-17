"""Email alert module for the auto-trader.

Sends alerts via SMTP (Gmail by default). Configure via environment variables:
  ALERT_SMTP_HOST      - SMTP host (default: smtp.gmail.com)
  ALERT_SMTP_PORT      - SMTP port (default: 587)
  ALERT_SMTP_USER      - Gmail address used to authenticate
  ALERT_SMTP_PASSWORD  - Gmail App Password (not your regular password)
  ALERT_EMAIL_FROM     - From address (defaults to ALERT_SMTP_USER)
  ALERT_EMAIL_TO       - Comma-separated list of recipient email addresses

All send functions log exceptions and never raise - alerts are best-effort.
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_DISCLAIMER = "This is automated technical analysis, not financial advice."


def configured() -> bool:
    """Return True if SMTP credentials are set in the environment."""
    return bool(os.environ.get("ALERT_SMTP_USER") and os.environ.get("ALERT_SMTP_PASSWORD"))


def _send(subject: str, body: str) -> None:
    """Internal: build and send one email. Silently logs any failure."""
    smtp_host = os.environ.get("ALERT_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("ALERT_SMTP_PORT", "587"))
    smtp_user = os.environ.get("ALERT_SMTP_USER", "")
    smtp_password = os.environ.get("ALERT_SMTP_PASSWORD", "")
    from_addr = os.environ.get("ALERT_EMAIL_FROM", smtp_user)
    to_raw = os.environ.get("ALERT_EMAIL_TO", "")
    recipients = [r.strip() for r in to_raw.split(",") if r.strip()]

    if not smtp_user or not smtp_password or not recipients:
        return

    full_body = f"{body}\n\n{_DISCLAIMER}"
    msg = MIMEText(full_body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_addr, recipients, msg.as_string())
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send alert email (subject: %s)", subject)


def alert_trade_placed(
    symbol: str,
    side: str,
    qty: float,
    price: float,
    confidence: float,
    order_id: str,
) -> None:
    """Alert that the auto-trader placed a real order."""
    if not configured():
        return
    side_label = side.upper()
    subject = f"[Auto-Trader] {side_label} {qty} {symbol} @ ${price:.2f}"
    body = (
        f"Auto-Trader placed a {side_label} order.\n\n"
        f"  Symbol:     {symbol}\n"
        f"  Side:       {side_label}\n"
        f"  Quantity:   {qty}\n"
        f"  Price:      ${price:.2f}\n"
        f"  Confidence: {confidence:.1f}%\n"
        f"  Order ID:   {order_id}"
    )
    _send(subject, body)


def alert_stop_loss_placed(
    symbol: str,
    qty: float,
    stop_price: float,
    entry_price: float,
) -> None:
    """Alert that a protective stop-loss order was placed after a BUY."""
    if not configured():
        return
    pct = (entry_price - stop_price) / entry_price * 100 if entry_price else 0
    subject = f"[Auto-Trader] Stop-loss set for {symbol} @ ${stop_price:.2f}"
    body = (
        f"A stop-limit sell order was placed to protect your {symbol} position.\n\n"
        f"  Symbol:      {symbol}\n"
        f"  Quantity:    {qty}\n"
        f"  Entry Price: ${entry_price:.2f}\n"
        f"  Stop Price:  ${stop_price:.2f} ({pct:.1f}% below entry)"
    )
    _send(subject, body)


def alert_circuit_breaker(loss_pct: float, max_loss_pct: float) -> None:
    """Alert that the circuit breaker halted trading for the day."""
    if not configured():
        return
    subject = "[Auto-Trader] CIRCUIT BREAKER TRIGGERED - Trading halted"
    body = (
        f"The auto-trader's daily circuit breaker has been triggered.\n\n"
        f"  Today's loss: {loss_pct:.1f}%\n"
        f"  Max allowed:  {max_loss_pct:.1f}%\n\n"
        f"Trading is halted for the rest of today."
    )
    _send(subject, body)


def alert_order_failed(symbol: str, side: str, error: str) -> None:
    """Alert that an order placement failed."""
    if not configured():
        return
    subject = f"[Auto-Trader] Order FAILED: {side.upper()} {symbol}"
    body = (
        f"The auto-trader failed to place an order.\n\n"
        f"  Symbol: {symbol}\n"
        f"  Side:   {side.upper()}\n"
        f"  Error:  {error}"
    )
    _send(subject, body)
