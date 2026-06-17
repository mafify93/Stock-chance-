"""AI Auto-Trader: an optional background loop that periodically evaluates
the combined AI signal (rule-based + ML + LLM, see `app.ai_combine`) for a
configured list of symbols and places REAL orders (via Alpaca or Questrade)
when conditions are met.

=== SAFETY MODEL - READ BEFORE ENABLING ===

- Disabled by default (`enabled: false`).
- `broker` selects which brokerage executes orders: "alpaca" (supports a
  simulated paper account) or "questrade" (Canadian brokerage, REAL MONEY
  ONLY - there is no paper-trading sandbox).
- For Alpaca with `environment: "live"`, and for Questrade ALWAYS, orders are
  only placed if `confirmed_real_money` is ALSO true - otherwise live
  decisions are logged as dry-runs only. This mirrors the iOS app's "Enable
  Live Trading" confirmation, but since this loop runs server-side without
  the app open, it needs its own explicit flag.
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
MUST persist credentials server-side to act while the app is closed: Alpaca
API keys, or a Questrade refresh token + account number. Questrade refresh
tokens are single-use and rotate on every exchange - the rotated token is
persisted back to this file automatically after each run. Credentials are
stored in `data/auto_trader_config.json` with file permissions set to 0600
(owner read/write only). This directory is gitignored. Only run this backend
on a machine you trust, and validate with Alpaca PAPER credentials (or
Questrade with `confirmed_real_money: false`, which dry-runs) before ever
enabling real-money trading.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from . import ai_analyst, earnings_sentiment, models, notifications
from .ai_combine import combine
from .intraday import get_market_session
from .ml.model import ml_predictor
from .providers import alpaca, questrade, sec_edgar, yahoo
from .signals import analyze
from .universe import DEFAULT_UNIVERSE

logger = logging.getLogger(__name__)

# On Render (and other cloud hosts), the container filesystem is ephemeral -
# runtime data is lost on every redeploy. Set PERSISTENT_DATA_DIR to a
# mounted persistent disk path (e.g. /data) so config and logs survive.
DATA_DIR = Path(os.environ.get("PERSISTENT_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
CONFIG_PATH = DATA_DIR / "auto_trader_config.json"
LOG_PATH = DATA_DIR / "auto_trader_log.json"
MAX_LOG_ENTRIES = 200

_DEFAULT_CONFIG = {
    "enabled": False,
    "broker": "alpaca",
    "symbols": [],
    # When True the engine ignores `symbols` and picks its own candidates each
    # cycle by screening a broad liquid universe (see `_select_symbols`).
    "auto_select": False,
    "auto_select_count": 5,
    # Risk control: never hold more than this many open positions at once.
    "max_open_positions": 5,
    "min_confidence": 70.0,
    "max_position_value": 100.0,
    "max_daily_trades": 3,
    "poll_interval_minutes": 15,
    "environment": "paper",
    "confirmed_real_money": False,
    "alpaca_api_key_id": None,
    "alpaca_api_secret_key": None,
    "questrade_refresh_token": None,
    "questrade_account_number": None,
    # Phase 2: Risk management
    "stop_loss_pct": 3.0,
    "max_daily_loss_pct": 5.0,
    "require_multi_timeframe": False,
    # Signal-quality factors
    "use_insider_signal": True,  # SEC Form 4 insider trading (free)
    "use_earnings_sentiment": False,  # Claude web-search earnings sentiment (costs API calls)
    "stop_orders": {},  # {symbol: order_id_string} — active stop-loss order IDs
    "circuit_breaker_date": None,  # ISO date string of last circuit-breaker check
    "circuit_breaker_start_equity": None,  # float equity at start of that trading day
}


class _BrokerSession:
    """Broker-agnostic interface the evaluation loop trades through."""

    def get_positions(self) -> dict[str, dict]:
        """Current positions keyed by symbol; each value has at least a
        `qty` key (float-able)."""
        raise NotImplementedError

    def place_order(self, symbol: str, qty: float, side: str) -> dict:
        """Places an order. `side` is `"buy"` or `"sell"`. Returns a dict
        with at least an `id` key."""
        raise NotImplementedError


class _AlpacaSession(_BrokerSession):
    def __init__(self, api_key: str, api_secret: str, base_url: str) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = base_url

    def get_positions(self) -> dict[str, dict]:
        positions = alpaca.get_positions(self._api_key, self._api_secret, self._base_url)
        return {p["symbol"]: p for p in positions}

    def place_order(self, symbol: str, qty: float, side: str) -> dict:
        return alpaca.place_order(self._api_key, self._api_secret, symbol, qty, side, base_url=self._base_url)


class _QuestradeSession(_BrokerSession):
    def __init__(self, access_token: str, api_server: str, account_number: str) -> None:
        self._access_token = access_token
        self._api_server = api_server
        self._account_number = account_number

    def get_positions(self) -> dict[str, dict]:
        positions = questrade.get_positions(self._access_token, self._api_server, self._account_number)
        return {p["symbol"]: {"symbol": p["symbol"], "qty": p["openQuantity"]} for p in positions}

    def _get_symbol_id(self, symbol: str) -> int:
        matches = questrade.search_symbols(self._access_token, self._api_server, symbol)
        match = next((s for s in matches if s.get("symbol") == symbol), None)
        if match is None:
            raise questrade.QuestradeError(404, f"Could not find a Questrade symbolId for {symbol}")
        return match["symbolId"]

    def place_order(self, symbol: str, qty: float, side: str) -> dict:
        symbol_id = self._get_symbol_id(symbol)
        order_side = "Buy" if side == "buy" else "Sell"
        data = questrade.place_order(
            self._access_token,
            self._api_server,
            self._account_number,
            symbol_id,
            qty,
            order_side,
        )
        placed = (data.get("orders") or [{}])[0]
        return {"id": placed.get("id", "")}

    def place_stop_limit_order(self, symbol: str, qty: float, stop_price: float, limit_price: float) -> dict:
        """Place a GoodTillCanceled stop-limit SELL order for risk management."""
        symbol_id = self._get_symbol_id(symbol)
        data = questrade.place_stop_limit_order(
            self._access_token,
            self._api_server,
            self._account_number,
            symbol_id,
            qty,
            "Sell",
            stop_price,
            limit_price,
        )
        placed = (data.get("orders") or [{}])[0]
        return {"id": placed.get("id", "")}

    def cancel_order(self, order_id: str) -> None:
        """Cancel an open order (e.g. a stop-loss) by order ID."""
        try:
            questrade.cancel_order(self._access_token, self._api_server, self._account_number, order_id)
        except questrade.QuestradeError:
            logger.exception("Failed to cancel Questrade order %s", order_id)

    def get_equity(self) -> float | None:
        """Return total account equity, or None if unavailable."""
        return questrade.get_account_equity(self._access_token, self._api_server, self._account_number)


class AutoTraderEngine:
    def __init__(self) -> None:
        self._lock = Lock()
        self._task: asyncio.Task | None = None
        self._retrain_task: asyncio.Task | None = None
        self._config = self._load_config()
        self._log = self._load_log()

    # --- persistence ---------------------------------------------------

    def _load_config(self) -> dict:
        # Seed from env vars first so credentials survive even a full disk wipe.
        # The saved file takes precedence (it holds the latest rotated token).
        env_overrides: dict = {}
        if os.environ.get("QUESTRADE_REFRESH_TOKEN"):
            env_overrides["questrade_refresh_token"] = os.environ["QUESTRADE_REFRESH_TOKEN"]
        if os.environ.get("QUESTRADE_ACCOUNT_NUMBER"):
            env_overrides["questrade_account_number"] = os.environ["QUESTRADE_ACCOUNT_NUMBER"]

        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH) as f:
                    data = json.load(f)
                return {**_DEFAULT_CONFIG, **env_overrides, **data}
            except Exception:  # noqa: BLE001
                logger.exception("Failed to load auto-trader config, using defaults")
        return {**_DEFAULT_CONFIG, **env_overrides}

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
                broker=c.get("broker", "alpaca"),
                symbols=list(c["symbols"]),
                auto_select=c.get("auto_select", False),
                auto_select_count=c.get("auto_select_count", 5),
                max_open_positions=c.get("max_open_positions", 5),
                min_confidence=c["min_confidence"],
                max_position_value=c["max_position_value"],
                max_daily_trades=c["max_daily_trades"],
                poll_interval_minutes=c["poll_interval_minutes"],
                environment=c["environment"],
                confirmed_real_money=c["confirmed_real_money"],
                alpaca_configured=bool(c.get("alpaca_api_key_id") and c.get("alpaca_api_secret_key")),
                questrade_configured=bool(c.get("questrade_refresh_token") and c.get("questrade_account_number")),
                stop_loss_pct=c.get("stop_loss_pct", 3.0),
                max_daily_loss_pct=c.get("max_daily_loss_pct", 5.0),
                require_multi_timeframe=c.get("require_multi_timeframe", False),
                use_insider_signal=c.get("use_insider_signal", True),
                use_earnings_sentiment=c.get("use_earnings_sentiment", False),
            )

    def update_config(self, req: models.AutoTraderConfigRequest) -> models.AutoTraderConfig:
        if req.environment not in ("paper", "live"):
            raise ValueError("environment must be 'paper' or 'live'")
        if req.broker not in ("alpaca", "questrade"):
            raise ValueError("broker must be 'alpaca' or 'questrade'")
        with self._lock:
            self._config["enabled"] = req.enabled
            self._config["broker"] = req.broker
            self._config["symbols"] = [s.upper() for s in req.symbols]
            self._config["auto_select"] = req.auto_select
            self._config["auto_select_count"] = max(1, min(20, req.auto_select_count))
            self._config["max_open_positions"] = max(1, min(50, req.max_open_positions))
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
            if req.questrade_refresh_token:
                self._config["questrade_refresh_token"] = req.questrade_refresh_token
            if req.questrade_account_number:
                self._config["questrade_account_number"] = req.questrade_account_number
            self._config["stop_loss_pct"] = max(0.0, req.stop_loss_pct)
            self._config["max_daily_loss_pct"] = max(0.0, req.max_daily_loss_pct)
            self._config["require_multi_timeframe"] = req.require_multi_timeframe
            self._config["use_insider_signal"] = req.use_insider_signal
            self._config["use_earnings_sentiment"] = req.use_earnings_sentiment
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
            "entry_price": decision.get("entry_price"),
        }
        with self._lock:
            self._log.append(entry)
            self._save_log()
        return entry

    # --- broker session -----------------------------------------------------

    def _build_session(self, config: dict) -> tuple[_BrokerSession | None, str | None]:
        """Builds a broker session for this run, or returns `(None, reason)`
        if credentials aren't configured (or Questrade auth fails)."""
        if config["broker"] == "questrade":
            return self._questrade_session(config)

        api_key = config.get("alpaca_api_key_id")
        api_secret = config.get("alpaca_api_secret_key")
        if not api_key or not api_secret:
            return None, "no Alpaca credentials configured"
        base_url = alpaca.LIVE_BASE_URL if config["environment"] == "live" else alpaca.PAPER_BASE_URL
        return _AlpacaSession(api_key, api_secret, base_url), None

    def _questrade_session(self, config: dict) -> tuple[_QuestradeSession | None, str | None]:
        refresh_token = config.get("questrade_refresh_token")
        account_number = config.get("questrade_account_number")
        if not refresh_token or not account_number:
            return None, "no Questrade credentials configured"

        try:
            data = questrade.refresh_access_token(refresh_token)
        except questrade.QuestradeError as exc:
            return None, f"Questrade auth failed: {exc}"

        # Questrade refresh tokens are single-use - persist the rotated token
        # immediately so the next run can still authenticate.
        with self._lock:
            self._config["questrade_refresh_token"] = data["refresh_token"]
            self._save_config()

        return _QuestradeSession(data["access_token"], data["api_server"], account_number), None

    # --- evaluation loop ------------------------------------------------------

    def run_once(self) -> list[dict]:
        """Evaluates every configured symbol once and returns the resulting
        log entries. Safe to call directly (e.g. a manual "run now" trigger)
        regardless of `enabled` - the background loop is what respects
        `enabled`."""
        with self._lock:
            config = dict(self._config)

        if get_market_session().status != "open":
            return []

        session, session_error = self._build_session(config)

        # --- Circuit breaker: track starting equity once per trading day ---
        today = datetime.now(timezone.utc).date().isoformat()
        if session is not None:
            cb_date = config.get("circuit_breaker_date")
            if cb_date != today:
                # New trading day — record starting equity
                equity = None
                if isinstance(session, _QuestradeSession):
                    equity = session.get_equity()
                elif isinstance(session, _AlpacaSession):
                    try:
                        acct = alpaca.get_account(session._api_key, session._api_secret, session._base_url)
                        equity = float(acct.get("equity", 0))
                    except Exception:  # noqa: BLE001
                        equity = None
                with self._lock:
                    self._config["circuit_breaker_date"] = today
                    if equity is not None:
                        self._config["circuit_breaker_start_equity"] = equity
                    self._save_config()
                config = dict(self._config)

            # Check circuit breaker
            start_equity = config.get("circuit_breaker_start_equity")
            max_daily_loss_pct = config.get("max_daily_loss_pct", 5.0)
            if start_equity and start_equity > 0:
                current_equity = None
                if isinstance(session, _QuestradeSession):
                    current_equity = session.get_equity()
                elif isinstance(session, _AlpacaSession):
                    try:
                        acct = alpaca.get_account(session._api_key, session._api_secret, session._base_url)
                        current_equity = float(acct.get("equity", 0))
                    except Exception:  # noqa: BLE001
                        current_equity = None
                if current_equity is not None:
                    loss_threshold = start_equity * (1 - max_daily_loss_pct / 100)
                    if current_equity < loss_threshold:
                        loss_pct = (start_equity - current_equity) / start_equity * 100
                        logger.warning(
                            "Circuit breaker triggered: equity %.2f < threshold %.2f (%.1f%% loss vs %.1f%% max)",
                            current_equity, loss_threshold, loss_pct, max_daily_loss_pct,
                        )
                        notifications.alert_circuit_breaker(loss_pct, max_daily_loss_pct)
                        return []

        positions_by_symbol: dict[str, dict] = {}
        if session is not None:
            try:
                positions_by_symbol = session.get_positions()
            except (alpaca.AlpacaError, questrade.QuestradeError):
                logger.exception("Could not fetch positions for auto-trader")

        symbols = self._symbols_to_evaluate(config, positions_by_symbol)
        if not symbols:
            return []

        with self._lock:
            trades_today = sum(
                1 for entry in self._log if entry["executed"] and entry["timestamp"].startswith(today)
            )

        entries = []
        for symbol in symbols:
            decision = self._evaluate_symbol(symbol, config, positions_by_symbol, trades_today, session, session_error)
            if decision["executed"]:
                trades_today += 1
            entries.append(self._record(decision))

        return entries

    def _symbols_to_evaluate(self, config: dict, positions_by_symbol: dict[str, dict]) -> list[str]:
        """The symbols to evaluate this cycle.

        In manual mode this is just the user's configured list. In
        auto-select mode the engine ignores that list and picks its own
        candidates (see `_select_symbols`). Either way, any symbol the
        account currently holds is always included so open positions can be
        evaluated for an exit."""
        if config.get("auto_select"):
            return self._select_symbols(config, positions_by_symbol)
        return list(config["symbols"])

    def _select_symbols(self, config: dict, positions_by_symbol: dict[str, dict]) -> list[str]:
        """Screen a broad liquid universe with the (cheap) rule-based signal
        and return the highest-conviction BUY candidates, plus every symbol
        currently held so it can be evaluated for an exit.

        This is the cheap first pass: only the resulting shortlist gets the
        full (heavier) combined ML + AI-analyst evaluation in
        `_evaluate_symbol`, so we don't run the LLM across the whole universe
        every cycle. Symbols are fetched in parallel (15 workers) so the
        full ~460-stock S&P 500 universe scans in roughly the same time as
        the old 80-stock sequential scan."""
        held = list(positions_by_symbol.keys())
        to_scan = [sym for sym in DEFAULT_UNIVERSE if sym not in held]

        def _scan_one(sym: str) -> tuple[str, float] | None:
            try:
                df = yahoo.get_history(sym, "1y", "1d")
                result = analyze(sym, df)
                if result.action in ("BUY", "STRONG_BUY"):
                    return (sym, result.score)
            except Exception:  # noqa: BLE001 - skip any symbol that won't load
                pass
            return None

        candidates: list[tuple[str, float]] = []
        with ThreadPoolExecutor(max_workers=15) as executor:
            for result in executor.map(_scan_one, to_scan):
                if result is not None:
                    candidates.append(result)

        candidates.sort(key=lambda item: item[1], reverse=True)
        top = [sym for sym, _ in candidates[: config.get("auto_select_count", 5)]]
        # Held positions first so exits are always considered before new buys.
        return held + top

    def _evaluate_symbol(
        self,
        symbol: str,
        config: dict,
        positions_by_symbol: dict[str, dict],
        trades_today: int,
        session: _BrokerSession | None,
        session_error: str | None,
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
        # Auxiliary factors - only run on the shortlist here, never in the
        # cheap universe-wide first pass (`_select_symbols`).
        insider_result = sec_edgar.get_insider_signal(symbol) if config.get("use_insider_signal") else None
        sentiment_result = (
            earnings_sentiment.get_sentiment(symbol)
            if config.get("use_earnings_sentiment") and earnings_sentiment.configured()
            else None
        )
        action, confidence = combine(signal_dict, ml_result, llm_result, insider_result, sentiment_result)

        # --- Phase 4: Multi-timeframe confirmation (opt-in) ---
        if config.get("require_multi_timeframe"):
            try:
                df_1h = yahoo.get_history(symbol, "60d", "1h")
                signal_1h = analyze(symbol, df_1h)
                daily_bullish = action in ("BUY", "STRONG_BUY")
                daily_bearish = action in ("SELL", "STRONG_SELL")
                h1_bullish = signal_1h.action in ("BUY", "STRONG_BUY")
                h1_bearish = signal_1h.action in ("SELL", "STRONG_SELL")
                agrees = (daily_bullish and h1_bullish) or (daily_bearish and h1_bearish)
                if not agrees:
                    return _decision(
                        symbol, "HOLD", confidence, False,
                        f"multi-timeframe disagreement: daily={action} 1h={signal_1h.action}",
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Multi-timeframe fetch failed for %s: %s", symbol, exc)

        if confidence < config["min_confidence"]:
            return _decision(symbol, action, confidence, False, f"confidence {confidence:.1f} below threshold {config['min_confidence']:.1f}")

        if action == "HOLD":
            return _decision(symbol, action, confidence, False, "combined signal is HOLD")

        if session is None:
            return _decision(symbol, action, confidence, False, session_error or "no broker credentials configured")

        if trades_today >= config["max_daily_trades"]:
            return _decision(symbol, action, confidence, False, f"daily trade limit reached ({config['max_daily_trades']})")

        existing = positions_by_symbol.get(symbol)

        if action in ("BUY", "STRONG_BUY"):
            if existing:
                return _decision(symbol, action, confidence, False, "already holding a position - not adding to it")
            max_open = config.get("max_open_positions", 0)
            if max_open and len(positions_by_symbol) >= max_open:
                return _decision(symbol, action, confidence, False, f"max open positions reached ({max_open})")

            # Phase 2c: Volatility-based position sizing (ATR-14)
            try:
                atr = df["High"].sub(df["Low"]).rolling(14).mean().iloc[-1]
                risk_budget = config["max_position_value"] * 0.02
                qty_atr = int(risk_budget / atr) if atr > 0 else 0
            except Exception:  # noqa: BLE001
                qty_atr = 0
            qty_fixed = int(config["max_position_value"] // signal_result.price)
            if qty_atr > 0:
                qty = max(1, min(qty_fixed, qty_atr))
            else:
                qty = qty_fixed

            if qty < 1:
                return _decision(symbol, action, confidence, False, f"max position value ${config['max_position_value']:.2f} buys less than 1 share at ${signal_result.price:.2f}")
            side = "buy"
        else:  # SELL / STRONG_SELL
            if not existing:
                return _decision(symbol, action, confidence, False, "no position held - nothing to sell")
            qty = float(existing["qty"])
            side = "sell"

        is_live = config["broker"] == "questrade" or config["environment"] == "live"
        if is_live and not config["confirmed_real_money"]:
            return _decision(symbol, action, confidence, False, f"DRY RUN - would {side} {qty} {symbol} but live trading not confirmed (set confirmed_real_money)")

        try:
            # Phase 2a: Before a Questrade SELL, cancel any active stop-loss order
            if side == "sell" and config["broker"] == "questrade" and isinstance(session, _QuestradeSession):
                existing_stop_id = config.get("stop_orders", {}).get(symbol)
                if existing_stop_id:
                    session.cancel_order(existing_stop_id)
                    with self._lock:
                        self._config.setdefault("stop_orders", {}).pop(symbol, None)
                        self._save_config()
                    config = dict(self._config)

            order = session.place_order(symbol, qty, side)
            order_id = str(order.get("id", ""))

            # Keep the in-cycle position map in sync so the open-position cap
            # and "already holding" checks stay accurate across this run.
            if side == "buy":
                positions_by_symbol[symbol] = {"symbol": symbol, "qty": qty}

                # Phase 2a: Place broker-side stop-loss for Questrade BUY
                if config["broker"] == "questrade" and isinstance(session, _QuestradeSession):
                    stop_loss_pct = config.get("stop_loss_pct", 3.0)
                    stop_price = round(signal_result.price * (1 - stop_loss_pct / 100), 4)
                    limit_price = round(stop_price * 0.99, 4)
                    try:
                        stop_order = session.place_stop_limit_order(symbol, qty, stop_price, limit_price)
                        stop_order_id = str(stop_order.get("id", ""))
                        with self._lock:
                            self._config.setdefault("stop_orders", {})[symbol] = stop_order_id
                            self._save_config()
                        config = dict(self._config)
                        logger.info(
                            "Placed stop-limit order %s for %s at stop=%.4f limit=%.4f",
                            stop_order_id, symbol, stop_price, limit_price,
                        )
                        notifications.alert_stop_loss_placed(symbol, qty, stop_price, signal_result.price)
                    except Exception:  # noqa: BLE001
                        logger.exception("Failed to place stop-loss order for %s", symbol)

                notifications.alert_trade_placed(symbol, side, qty, signal_result.price, confidence, order_id)
            else:
                positions_by_symbol.pop(symbol, None)
                notifications.alert_trade_placed(symbol, side, qty, signal_result.price, confidence, order_id)

            return _decision(
                symbol, action, confidence, True,
                f"placed {side} order for {qty} {symbol}",
                order_id=order_id,
                entry_price=signal_result.price,
            )
        except (alpaca.AlpacaError, questrade.QuestradeError) as exc:
            notifications.alert_order_failed(symbol, side, str(exc))
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

    async def _retrain_loop(self) -> None:
        """Phase 4: Retrain the ML model weekly as a background task."""
        _RETRAIN_INTERVAL = 7 * 24 * 3600  # 7 days in seconds
        while True:
            await asyncio.sleep(_RETRAIN_INTERVAL)
            logger.info("Starting weekly ML model retraining...")
            try:
                import subprocess
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["python", "-m", "scripts.train_ml_model"],
                    capture_output=True,
                    text=True,
                    timeout=3600,
                )
                if result.returncode == 0:
                    logger.info("ML model retrained successfully")
                    ml_predictor._loaded = False  # force reload on next prediction
                else:
                    logger.error("ML retraining failed (exit %d): %s", result.returncode, result.stderr)
            except Exception:  # noqa: BLE001
                logger.exception("ML retraining subprocess failed")

    # --- holdings / emergency sell ----------------------------------------

    def get_positions_with_pnl(self) -> list[models.AutoTraderPosition]:
        """Return tracked open positions enriched with current price and P&L."""
        with self._lock:
            entries = dict(self._config.get("position_entries", {}))

        result = []
        for symbol, entry_price in entries.items():
            current_price = None
            pnl_pct = None
            pnl_dollar = None
            try:
                df = yahoo.get_history(symbol, "5d", "1d")
                if not df.empty:
                    current_price = float(df["Close"].iloc[-1])
                    if entry_price and entry_price > 0:
                        pnl_pct = (current_price - entry_price) / entry_price * 100
                        pnl_dollar = current_price - entry_price
            except Exception:  # noqa: BLE001
                logger.warning("Could not fetch current price for %s", symbol)
            result.append(models.AutoTraderPosition(
                symbol=symbol,
                entry_price=entry_price,
                current_price=current_price,
                pnl_pct=pnl_pct,
                pnl_dollar=pnl_dollar,
            ))
        return result

    def sell_all(self) -> models.SellAllResponse:
        """Emergency liquidation: sell every tracked position immediately."""
        with self._lock:
            config = dict(self._config)

        entries = dict(config.get("position_entries", {}))
        if not entries:
            return models.SellAllResponse(sold=[], errors=[], message="No tracked positions to sell.")

        session, session_error = self._build_session(config)
        if session is None:
            return models.SellAllResponse(
                sold=[],
                errors=[{"reason": session_error or "no broker credentials"}],
                message=f"Cannot connect to broker: {session_error}",
            )

        try:
            positions_by_symbol = session.get_positions()
        except Exception as exc:  # noqa: BLE001
            return models.SellAllResponse(
                sold=[],
                errors=[{"reason": f"Failed to fetch broker positions: {exc}"}],
                message=f"Failed to fetch broker positions: {exc}",
            )

        sold: list[str] = []
        errors: list[dict] = []

        for symbol in list(entries.keys()):
            try:
                # Cancel any pending stop-loss order first
                if config.get("broker") == "questrade" and isinstance(session, _QuestradeSession):
                    stop_id = config.get("stop_orders", {}).get(symbol)
                    if stop_id:
                        session.cancel_order(stop_id)

                broker_pos = positions_by_symbol.get(symbol)
                if broker_pos is None:
                    # Position already closed broker-side - just clean up tracking
                    with self._lock:
                        self._config.get("position_entries", {}).pop(symbol, None)
                        self._config.get("position_highs", {}).pop(symbol, None)
                        self._config.get("stop_orders", {}).pop(symbol, None)
                        self._save_config()
                    config = dict(self._config)
                    continue

                qty = float(broker_pos["qty"])
                if qty <= 0:
                    continue

                order = session.place_order(symbol, qty, "sell")
                order_id = str(order.get("id", ""))

                with self._lock:
                    self._config.get("position_entries", {}).pop(symbol, None)
                    self._config.get("position_highs", {}).pop(symbol, None)
                    self._config.get("stop_orders", {}).pop(symbol, None)
                    self._save_config()
                config = dict(self._config)

                sold.append(symbol)
                self._record({
                    "symbol": symbol,
                    "action": "SELL",
                    "combined_confidence": 100.0,
                    "executed": True,
                    "reason": "emergency sell-all",
                    "order_id": order_id,
                })
            except Exception as exc:  # noqa: BLE001
                errors.append({"symbol": symbol, "reason": str(exc)})
                logger.exception("sell_all failed for %s", symbol)

        if sold and not errors:
            message = f"Sold {len(sold)} position(s): {', '.join(sold)}"
        elif sold:
            message = f"Sold {len(sold)}: {', '.join(sold)}. {len(errors)} error(s)."
        else:
            message = "All sells failed. Check broker connection and try again."

        return models.SellAllResponse(sold=sold, errors=errors, message=message)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
        if self._retrain_task is None:
            self._retrain_task = asyncio.create_task(self._retrain_loop())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._retrain_task is not None:
            self._retrain_task.cancel()
            self._retrain_task = None


def _decision(
    symbol: str,
    action: str,
    confidence: float,
    executed: bool,
    reason: str,
    order_id: str | None = None,
    entry_price: float | None = None,
) -> dict:
    return {
        "symbol": symbol,
        "action": action,
        "combined_confidence": confidence,
        "executed": executed,
        "reason": reason,
        "order_id": order_id,
        "entry_price": entry_price,
    }


auto_trader = AutoTraderEngine()
