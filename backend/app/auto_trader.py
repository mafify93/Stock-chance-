"""AI Auto-Trader: an optional background loop that periodically evaluates
the combined AI signal (rule-based + ML + LLM, see `app.ai_combine`) for a
configured list of symbols and places REAL Alpaca orders when conditions are
met.

=== SAFETY MODEL - READ BEFORE ENABLING ===

- Disabled by default (`enabled: false`).
- For `environment: "live"`, orders are only placed if `confirmed_real_money`
  is ALSO true - otherwise live decisions are logged as dry-runs only. This
  mirrors the iOS app's "Enable Live Trading" confirmation, but since this
  loop runs server-side without the app open, it needs its own explicit flag.
- `min_confidence` (0-100) gates every trade - the combined signal must clear
  this bar before anything happens.
- `max_position_value` caps the dollar size of any single BUY (an existing
  position is never added to - "no pyramiding").
- `max_daily_trades` caps how many orders can be placed per UTC day.
- Only evaluates symbols while the US market is open.
- Every decision (including HOLDs and skipped trades, with the reason why)
  is appended to `data/auto_trader_log.json` so you can audit exactly what it
  did and why.

=== CREDENTIAL STORAGE ===

Unlike the rest of this backend (which is stateless and never stores
brokerage credentials - the iOS app sends them per-request), the auto-trader
MUST persist Alpaca API keys server-side to act while the app is closed.
They're stored in `data/auto_trader_config.json` with file permissions set to
0600 (owner read/write only). This directory is gitignored. Only run this
backend on a machine you trust, and validate with Alpaca PAPER credentials
before ever switching to `live`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from . import ai_analyst, models
from .ai_combine import combine
from .intraday import get_market_session
from .ml.model import ml_predictor
from .providers import alpaca, yahoo
from .signals import analyze

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CONFIG_PATH = DATA_DIR / "auto_trader_config.json"
LOG_PATH = DATA_DIR / "auto_trader_log.json"
MAX_LOG_ENTRIES = 200

_DEFAULT_CONFIG = {
    "enabled": False,
    "symbols": [],
    "min_confidence": 70.0,
    "max_position_value": 100.0,
    "max_daily_trades": 3,
    "poll_interval_minutes": 15,
    "environment": "paper",
    "confirmed_real_money": False,
    "alpaca_api_key_id": None,
    "alpaca_api_secret_key": None,
}


class AutoTraderEngine:
    def __init__(self) -> None:
        self._lock = Lock()
        self._task: asyncio.Task | None = None
        self._config = self._load_config()
        self._log = self._load_log()

    # --- persistence ---------------------------------------------------

    def _load_config(self) -> dict:
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH) as f:
                    data = json.load(f)
                return {**_DEFAULT_CONFIG, **data}
            except Exception:  # noqa: BLE001
                logger.exception("Failed to load auto-trader config, using defaults")
        return dict(_DEFAULT_CONFIG)

    def _save_config(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(self._config, f, indent=2)
        os.chmod(CONFIG_PATH, 0o600)

    def _load_log(self) -> list[dict]:
        if LOG_PATH.exists():
            try:
                with open(LOG_PATH) as f:
                    return json.load(f)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to load auto-trader log")
        return []

    def _save_log(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "w") as f:
            json.dump(self._log[-MAX_LOG_ENTRIES:], f, indent=2)
        os.chmod(LOG_PATH, 0o600)

    # --- config -----------------------------------------------------------

    def get_config(self) -> models.AutoTraderConfig:
        with self._lock:
            c = self._config
            return models.AutoTraderConfig(
                enabled=c["enabled"],
                symbols=list(c["symbols"]),
                min_confidence=c["min_confidence"],
                max_position_value=c["max_position_value"],
                max_daily_trades=c["max_daily_trades"],
                poll_interval_minutes=c["poll_interval_minutes"],
                environment=c["environment"],
                confirmed_real_money=c["confirmed_real_money"],
                alpaca_configured=bool(c.get("alpaca_api_key_id") and c.get("alpaca_api_secret_key")),
            )

    def update_config(self, req: models.AutoTraderConfigRequest) -> models.AutoTraderConfig:
        if req.environment not in ("paper", "live"):
            raise ValueError("environment must be 'paper' or 'live'")
        with self._lock:
            self._config["enabled"] = req.enabled
            self._config["symbols"] = [s.upper() for s in req.symbols]
            self._config["min_confidence"] = max(0.0, min(100.0, req.min_confidence))
            self._config["max_position_value"] = max(0.0, req.max_position_value)
            self._config["max_daily_trades"] = max(0, req.max_daily_trades)
            self._config["poll_interval_minutes"] = max(5, req.poll_interval_minutes)
            self._config["environment"] = req.environment
            self._config["confirmed_real_money"] = req.confirmed_real_money
            # Only overwrite stored credentials if new ones were sent, so the
            # caller can update other settings without resending secrets.
            if req.alpaca_api_key_id:
                self._config["alpaca_api_key_id"] = req.alpaca_api_key_id
            if req.alpaca_api_secret_key:
                self._config["alpaca_api_secret_key"] = req.alpaca_api_secret_key
            self._save_config()
        return self.get_config()

    # --- status / log -------------------------------------------------------

    def get_status(self) -> models.AutoTraderStatus:
        with self._lock:
            today = datetime.now(timezone.utc).date().isoformat()
            trades_today = sum(
                1 for entry in self._log if entry["executed"] and entry["timestamp"].startswith(today)
            )
            decisions = [models.AutoTraderDecision(**d) for d in reversed(self._log[-50:])]
            last_run_at = self._log[-1]["timestamp"] if self._log else None
        return models.AutoTraderStatus(
            config=self.get_config(),
            last_run_at=last_run_at,
            trades_today=trades_today,
            decisions=decisions,
        )

    def _record(self, decision: dict) -> dict:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": decision["symbol"],
            "action": decision["action"],
            "combined_confidence": decision["combined_confidence"],
            "executed": decision["executed"],
            "reason": decision["reason"],
            "order_id": decision.get("order_id"),
        }
        with self._lock:
            self._log.append(entry)
            self._save_log()
        return entry

    # --- evaluation loop ------------------------------------------------------

    def run_once(self) -> list[dict]:
        """Evaluates every configured symbol once and returns the resulting
        log entries. Safe to call directly (e.g. a manual "run now" trigger)
        regardless of `enabled` - the background loop is what respects
        `enabled`."""
        with self._lock:
            config = dict(self._config)

        if not config["symbols"]:
            return []

        if get_market_session().status != "open":
            return []

        base_url = alpaca.LIVE_BASE_URL if config["environment"] == "live" else alpaca.PAPER_BASE_URL
        api_key = config.get("alpaca_api_key_id")
        api_secret = config.get("alpaca_api_secret_key")

        positions_by_symbol: dict[str, dict] = {}
        if api_key and api_secret:
            try:
                positions = alpaca.get_positions(api_key, api_secret, base_url)
                positions_by_symbol = {p["symbol"]: p for p in positions}
            except alpaca.AlpacaError:
                logger.exception("Could not fetch positions for auto-trader")

        today = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            trades_today = sum(
                1 for entry in self._log if entry["executed"] and entry["timestamp"].startswith(today)
            )

        entries = []
        for symbol in config["symbols"]:
            decision = self._evaluate_symbol(symbol, config, positions_by_symbol, trades_today, api_key, api_secret, base_url)
            if decision["executed"]:
                trades_today += 1
            entries.append(self._record(decision))

        return entries

    def _evaluate_symbol(
        self,
        symbol: str,
        config: dict,
        positions_by_symbol: dict[str, dict],
        trades_today: int,
        api_key: str | None,
        api_secret: str | None,
        base_url: str,
    ) -> dict:
        try:
            df = yahoo.get_history(symbol, "1y", "1d")
            signal_result = analyze(symbol, df)
        except Exception as exc:  # noqa: BLE001
            return _decision(symbol, "HOLD", 0.0, False, f"data error: {exc}")

        signal_dict = {
            "action": signal_result.action,
            "score": signal_result.score,
            "confidence": signal_result.confidence,
            "price": signal_result.price,
            "reasons": signal_result.reasons,
        }
        ml_result = ml_predictor.predict(df)
        llm_result = ai_analyst.analyze(symbol, signal_dict, ml_result) if ai_analyst.configured() else None
        action, confidence = combine(signal_dict, ml_result, llm_result)

        if confidence < config["min_confidence"]:
            return _decision(symbol, action, confidence, False, f"confidence {confidence:.1f} below threshold {config['min_confidence']:.1f}")

        if action == "HOLD":
            return _decision(symbol, action, confidence, False, "combined signal is HOLD")

        if not api_key or not api_secret:
            return _decision(symbol, action, confidence, False, "no Alpaca credentials configured")

        if trades_today >= config["max_daily_trades"]:
            return _decision(symbol, action, confidence, False, f"daily trade limit reached ({config['max_daily_trades']})")

        existing = positions_by_symbol.get(symbol)

        if action == "BUY":
            if existing:
                return _decision(symbol, action, confidence, False, "already holding a position - not adding to it")
            qty = int(config["max_position_value"] // signal_result.price)
            if qty < 1:
                return _decision(symbol, action, confidence, False, f"max position value ${config['max_position_value']:.2f} buys less than 1 share at ${signal_result.price:.2f}")
            side = "buy"
        else:  # SELL
            if not existing:
                return _decision(symbol, action, confidence, False, "no position held - nothing to sell")
            qty = float(existing["qty"])
            side = "sell"

        if config["environment"] == "live" and not config["confirmed_real_money"]:
            return _decision(symbol, action, confidence, False, f"DRY RUN - would {side} {qty} {symbol} but live trading not confirmed (set confirmed_real_money)")

        try:
            order = alpaca.place_order(api_key, api_secret, symbol, qty, side, base_url=base_url)
            return _decision(symbol, action, confidence, True, f"placed {side} order for {qty} {symbol}", order_id=str(order.get("id", "")))
        except alpaca.AlpacaError as exc:
            return _decision(symbol, action, confidence, False, f"order failed: {exc}")

    # --- background task --------------------------------------------------

    async def _loop(self) -> None:
        while True:
            with self._lock:
                enabled = self._config.get("enabled", False)
                interval_minutes = self._config.get("poll_interval_minutes", 15)
            try:
                if enabled:
                    await asyncio.to_thread(self.run_once)
            except Exception:  # noqa: BLE001
                logger.exception("Auto-trader loop iteration failed")
            await asyncio.sleep(max(60, interval_minutes * 60))

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None


def _decision(symbol: str, action: str, confidence: float, executed: bool, reason: str, order_id: str | None = None) -> dict:
    return {
        "symbol": symbol,
        "action": action,
        "combined_confidence": confidence,
        "executed": executed,
        "reason": reason,
        "order_id": order_id,
    }


auto_trader = AutoTraderEngine()
