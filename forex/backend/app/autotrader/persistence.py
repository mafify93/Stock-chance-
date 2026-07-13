"""Encrypted, on-disk persistence of the bot's runtime state.

This lets the bot survive a container restart (a Render redeploy, instance
recycle, or crash). The running flag, OANDA credentials, config, and daily
accounting are written — encrypted — to a file on a persistent disk, and
reloaded on startup so the bot auto-resumes unattended.

Security
────────
The OANDA token is encrypted at rest with Fernet (AES-128-CBC + HMAC). The key
comes from the STATE_KEY environment variable (recommended in production). If
STATE_KEY is unset, a key is generated and stored on the same disk — functional,
but weaker, because anyone with disk access then has both halves. Set STATE_KEY.

All functions are best-effort and never raise into the caller: if persistence
fails, the bot still runs, it just won't auto-resume.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import logging
import os
import tempfile
from datetime import date

from cryptography.fernet import Fernet

from .config import AutoTraderConfig
from .state import BotState, TradeRecord, bot_state

log = logging.getLogger(__name__)

# Where the encrypted state lives. On Render this should point at a mounted
# persistent disk (set STATE_DIR=/var/data). Locally it falls back to a folder
# under the backend so dev runs don't need any setup.
_DEFAULT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".botstate"))


def _state_dir() -> str:
    return os.environ.get("STATE_DIR", _DEFAULT_DIR)


def _state_file() -> str:
    return os.path.join(_state_dir(), "bot_state.enc")


def _key_file() -> str:
    return os.path.join(_state_dir(), ".statekey")


def _get_fernet() -> Fernet | None:
    """Build the Fernet cipher from STATE_KEY, or a generated on-disk key."""
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        env_key = os.environ.get("STATE_KEY")
        if env_key:
            # Accept any string: derive a valid 32-byte Fernet key from it.
            digest = hashlib.sha256(env_key.encode()).digest()
            return Fernet(base64.urlsafe_b64encode(digest))

        key_path = _key_file()
        if os.path.exists(key_path):
            with open(key_path, "rb") as fh:
                return Fernet(fh.read().strip())

        key = Fernet.generate_key()
        with open(key_path, "wb") as fh:
            fh.write(key)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        log.warning(
            "persistence: STATE_KEY not set — generated a local key on disk. "
            "Set STATE_KEY env var for stronger encryption."
        )
        return Fernet(key)
    except Exception as exc:
        log.error(f"persistence: could not initialise encryption: {exc}")
        return None


def _snapshot(state: BotState) -> dict:
    return {
        "running": state.running,
        "halted": state.halted,
        "halt_reason": state.halt_reason,
        "token": state.token,
        "account_id": state.account_id,
        "environment": state.environment,
        "config": dataclasses.asdict(state.config),
        "session_date": state.session_date.isoformat() if state.session_date else None,
        "start_of_day_balance": state.start_of_day_balance,
        "account_start_balance": state.account_start_balance,
        "daily_pl": state.daily_pl,
        "trades_today": state.trades_today,
        "consecutive_losses": state.consecutive_losses,
        "risk_scale": state.risk_scale,
        "trades": [dataclasses.asdict(t) for t in state.trades],
    }


def save_state() -> None:
    """Encrypt and atomically write the current bot state to disk."""
    fernet = _get_fernet()
    if fernet is None:
        return
    try:
        payload = json.dumps(_snapshot(bot_state)).encode()
        blob = fernet.encrypt(payload)
        fd, tmp = tempfile.mkstemp(dir=_state_dir())
        with os.fdopen(fd, "wb") as fh:
            fh.write(blob)
        os.replace(tmp, _state_file())  # atomic on POSIX
    except Exception as exc:
        log.error(f"persistence: save failed (non-fatal): {exc}")


def load_into_state() -> bool:
    """Decrypt the saved state into bot_state. Returns True if it was running."""
    fernet = _get_fernet()
    if fernet is None or not os.path.exists(_state_file()):
        return False
    try:
        with open(_state_file(), "rb") as fh:
            snap = json.loads(fernet.decrypt(fh.read()))
    except Exception as exc:
        log.error(f"persistence: load failed (starting fresh): {exc}")
        return False

    try:
        cfg = AutoTraderConfig(**snap.get("config", {}))
    except Exception:
        cfg = AutoTraderConfig()

    try:
        trades = [TradeRecord(**t) for t in snap.get("trades", [])]
    except Exception:
        trades = []

    with bot_state._lock:
        bot_state.running = bool(snap.get("running", False))
        bot_state.halted = bool(snap.get("halted", False))
        bot_state.halt_reason = snap.get("halt_reason", "")
        bot_state.token = snap.get("token", "")
        bot_state.account_id = snap.get("account_id", "")
        bot_state.environment = snap.get("environment", "practice")
        bot_state.config = cfg
        sd = snap.get("session_date")
        bot_state.session_date = date.fromisoformat(sd) if sd else None
        bot_state.start_of_day_balance = snap.get("start_of_day_balance")
        bot_state.account_start_balance = snap.get("account_start_balance")
        bot_state.daily_pl = float(snap.get("daily_pl", 0.0))
        bot_state.trades_today = int(snap.get("trades_today", 0))
        bot_state.consecutive_losses = int(snap.get("consecutive_losses", 0))
        bot_state.risk_scale = float(snap.get("risk_scale", 1.0))
        bot_state.trades = trades

    return bot_state.running
