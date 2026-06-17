import json

import numpy as np
import pandas as pd
import pytest

from app import auto_trader as auto_trader_module
from app import models
from app.auto_trader import AutoTraderEngine
from app.intraday import MarketSession
from app.signals import SignalResult


def _trending_df(n=300, drift=0.3, seed=1):
    rng = np.random.default_rng(seed)
    base = 100 + np.cumsum(drift + rng.normal(0, 1, n))
    high = base + rng.uniform(0, 1, n)
    low = base - rng.uniform(0, 1, n)
    close = base
    open_ = base + rng.normal(0, 0.5, n)
    volume = rng.uniform(1e6, 5e6, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}, index=idx)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(auto_trader_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(auto_trader_module, "CONFIG_PATH", tmp_path / "auto_trader_config.json")
    monkeypatch.setattr(auto_trader_module, "LOG_PATH", tmp_path / "auto_trader_log.json")
    monkeypatch.setattr(auto_trader_module.ai_analyst, "configured", lambda: False)
    return AutoTraderEngine()


def test_default_config_is_disabled(engine):
    config = engine.get_config()
    assert config.enabled is False
    assert config.broker == "alpaca"
    assert config.environment == "paper"
    assert config.confirmed_real_money is False
    assert config.alpaca_configured is False
    assert config.questrade_configured is False
    assert config.auto_select is False
    assert config.auto_select_count == 5
    assert config.max_open_positions == 5


def test_update_config_persists_and_reloads(engine):
    req = models.AutoTraderConfigRequest(
        enabled=True,
        symbols=["aapl", "msft"],
        min_confidence=65,
        max_position_value=250,
        max_daily_trades=2,
        environment="paper",
        alpaca_api_key_id="key",
        alpaca_api_secret_key="secret",
    )
    config = engine.update_config(req)
    assert config.symbols == ["AAPL", "MSFT"]
    assert config.alpaca_configured is True

    config_path = auto_trader_module.CONFIG_PATH
    assert config_path.exists()
    on_disk = json.loads(config_path.read_text())
    assert on_disk["alpaca_api_key_id"] == "key"

    reloaded = AutoTraderEngine()
    assert reloaded.get_config().symbols == ["AAPL", "MSFT"]


def test_update_config_rejects_invalid_environment(engine):
    req = models.AutoTraderConfigRequest(environment="bogus")
    with pytest.raises(ValueError):
        engine.update_config(req)


def test_update_config_rejects_invalid_broker(engine):
    req = models.AutoTraderConfigRequest(broker="bogus")
    with pytest.raises(ValueError):
        engine.update_config(req)


def test_update_config_persists_questrade_credentials(engine):
    req = models.AutoTraderConfigRequest(
        broker="questrade",
        symbols=["aapl"],
        questrade_refresh_token="refresh-1",
        questrade_account_number="12345678",
    )
    config = engine.update_config(req)
    assert config.broker == "questrade"
    assert config.questrade_configured is True

    on_disk = json.loads(auto_trader_module.CONFIG_PATH.read_text())
    assert on_disk["questrade_refresh_token"] == "refresh-1"
    assert on_disk["questrade_account_number"] == "12345678"


def test_run_once_does_nothing_with_no_symbols(engine):
    assert engine.run_once() == []


def test_run_once_skips_when_market_closed(engine, monkeypatch):
    monkeypatch.setattr(auto_trader_module, "get_market_session", lambda: MarketSession(status="closed", now_et="x"))
    engine.update_config(models.AutoTraderConfigRequest(enabled=True, symbols=["AAPL"]))
    assert engine.run_once() == []


def test_run_once_holds_below_confidence_threshold(engine, monkeypatch):
    monkeypatch.setattr(auto_trader_module, "get_market_session", lambda: MarketSession(status="open", now_et="x"))
    monkeypatch.setattr(auto_trader_module.yahoo, "get_history", lambda *a, **k: _trending_df())
    monkeypatch.setattr(
        auto_trader_module, "analyze",
        lambda symbol, df: SignalResult(symbol=symbol, action="HOLD", score=0.05, confidence=10, price=100.0, reasons=["meh"]),
    )
    monkeypatch.setattr(auto_trader_module.ml_predictor, "predict", lambda df: None)

    engine.update_config(models.AutoTraderConfigRequest(enabled=True, symbols=["AAPL"], min_confidence=70))
    entries = engine.run_once()
    assert len(entries) == 1
    assert entries[0]["executed"] is False
    assert "below threshold" in entries[0]["reason"]


def test_run_once_buys_when_confident_and_no_position(engine, monkeypatch):
    monkeypatch.setattr(auto_trader_module, "get_market_session", lambda: MarketSession(status="open", now_et="x"))
    monkeypatch.setattr(auto_trader_module.yahoo, "get_history", lambda *a, **k: _trending_df())
    monkeypatch.setattr(
        auto_trader_module, "analyze",
        lambda symbol, df: SignalResult(symbol=symbol, action="STRONG_BUY", score=0.9, confidence=95, price=100.0, reasons=["strong uptrend"]),
    )
    monkeypatch.setattr(auto_trader_module.ml_predictor, "predict", lambda df: None)
    monkeypatch.setattr(auto_trader_module.alpaca, "get_positions", lambda *a, **k: [])

    placed = {}

    def fake_place_order(api_key, api_secret, symbol, qty, side, base_url=None):
        placed["args"] = (symbol, qty, side, base_url)
        return {"id": "order-123"}

    monkeypatch.setattr(auto_trader_module.alpaca, "place_order", fake_place_order)

    engine.update_config(models.AutoTraderConfigRequest(
        enabled=True, symbols=["AAPL"], min_confidence=50, max_position_value=1000,
        environment="paper", alpaca_api_key_id="key", alpaca_api_secret_key="secret",
    ))
    entries = engine.run_once()
    assert len(entries) == 1
    assert entries[0]["executed"] is True
    assert entries[0]["order_id"] == "order-123"
    assert placed["args"][2] == "buy"
    assert placed["args"][3] == auto_trader_module.alpaca.PAPER_BASE_URL


def test_run_once_live_without_confirmation_is_dry_run(engine, monkeypatch):
    monkeypatch.setattr(auto_trader_module, "get_market_session", lambda: MarketSession(status="open", now_et="x"))
    monkeypatch.setattr(auto_trader_module.yahoo, "get_history", lambda *a, **k: _trending_df())
    monkeypatch.setattr(
        auto_trader_module, "analyze",
        lambda symbol, df: SignalResult(symbol=symbol, action="STRONG_BUY", score=0.9, confidence=95, price=100.0, reasons=["strong uptrend"]),
    )
    monkeypatch.setattr(auto_trader_module.ml_predictor, "predict", lambda df: None)
    monkeypatch.setattr(auto_trader_module.alpaca, "get_positions", lambda *a, **k: [])

    def fail_place_order(*args, **kwargs):
        raise AssertionError("should not place a live order without confirmation")

    monkeypatch.setattr(auto_trader_module.alpaca, "place_order", fail_place_order)

    engine.update_config(models.AutoTraderConfigRequest(
        enabled=True, symbols=["AAPL"], min_confidence=50, max_position_value=1000,
        environment="live", confirmed_real_money=False,
        alpaca_api_key_id="key", alpaca_api_secret_key="secret",
    ))
    entries = engine.run_once()
    assert entries[0]["executed"] is False
    assert "DRY RUN" in entries[0]["reason"]


def test_run_once_sells_existing_position(engine, monkeypatch):
    monkeypatch.setattr(auto_trader_module, "get_market_session", lambda: MarketSession(status="open", now_et="x"))
    monkeypatch.setattr(auto_trader_module.yahoo, "get_history", lambda *a, **k: _trending_df())
    monkeypatch.setattr(
        auto_trader_module, "analyze",
        lambda symbol, df: SignalResult(symbol=symbol, action="STRONG_SELL", score=-0.9, confidence=95, price=100.0, reasons=["strong downtrend"]),
    )
    monkeypatch.setattr(auto_trader_module.ml_predictor, "predict", lambda df: None)
    monkeypatch.setattr(auto_trader_module.alpaca, "get_positions", lambda *a, **k: [{"symbol": "AAPL", "qty": "3"}])

    placed = {}

    def fake_place_order(api_key, api_secret, symbol, qty, side, base_url=None):
        placed["args"] = (symbol, qty, side)
        return {"id": "order-456"}

    monkeypatch.setattr(auto_trader_module.alpaca, "place_order", fake_place_order)

    engine.update_config(models.AutoTraderConfigRequest(
        enabled=True, symbols=["AAPL"], min_confidence=50, max_position_value=1000,
        environment="paper", alpaca_api_key_id="key", alpaca_api_secret_key="secret",
    ))
    entries = engine.run_once()
    assert entries[0]["executed"] is True
    assert placed["args"] == ("AAPL", 3.0, "sell")


def test_run_once_buys_with_questrade_and_persists_rotated_token(engine, monkeypatch):
    monkeypatch.setattr(auto_trader_module, "get_market_session", lambda: MarketSession(status="open", now_et="x"))
    monkeypatch.setattr(auto_trader_module.yahoo, "get_history", lambda *a, **k: _trending_df())
    monkeypatch.setattr(
        auto_trader_module, "analyze",
        lambda symbol, df: SignalResult(symbol=symbol, action="STRONG_BUY", score=0.9, confidence=95, price=100.0, reasons=["strong uptrend"]),
    )
    monkeypatch.setattr(auto_trader_module.ml_predictor, "predict", lambda df: None)

    monkeypatch.setattr(
        auto_trader_module.questrade, "refresh_access_token",
        lambda refresh_token: {
            "access_token": "access-2",
            "api_server": "https://api.questrade.com",
            "refresh_token": "refresh-2",
            "expires_in": 1800,
            "token_type": "Bearer",
        },
    )
    monkeypatch.setattr(auto_trader_module.questrade, "get_positions", lambda *a, **k: [])
    monkeypatch.setattr(
        auto_trader_module.questrade, "search_symbols",
        lambda access_token, api_server, prefix: [{"symbol": "AAPL", "symbolId": 8049, "description": "Apple Inc."}],
    )

    placed = {}

    def fake_place_order(access_token, api_server, account_number, symbol_id, quantity, side, **kwargs):
        placed["args"] = (account_number, symbol_id, quantity, side)
        return {"orders": [{"id": 555}]}

    monkeypatch.setattr(auto_trader_module.questrade, "place_order", fake_place_order)

    engine.update_config(models.AutoTraderConfigRequest(
        enabled=True, broker="questrade", symbols=["AAPL"], min_confidence=50, max_position_value=1000,
        confirmed_real_money=True, questrade_refresh_token="refresh-1", questrade_account_number="12345678",
    ))
    entries = engine.run_once()
    assert entries[0]["executed"] is True
    assert entries[0]["order_id"] == "555"
    assert placed["args"] == ("12345678", 8049, 10, "Buy")

    # The single-use refresh token must be rotated and persisted.
    assert engine.get_config().broker == "questrade"
    on_disk = json.loads(auto_trader_module.CONFIG_PATH.read_text())
    assert on_disk["questrade_refresh_token"] == "refresh-2"


def test_run_once_questrade_without_confirmation_is_dry_run(engine, monkeypatch):
    monkeypatch.setattr(auto_trader_module, "get_market_session", lambda: MarketSession(status="open", now_et="x"))
    monkeypatch.setattr(auto_trader_module.yahoo, "get_history", lambda *a, **k: _trending_df())
    monkeypatch.setattr(
        auto_trader_module, "analyze",
        lambda symbol, df: SignalResult(symbol=symbol, action="STRONG_BUY", score=0.9, confidence=95, price=100.0, reasons=["strong uptrend"]),
    )
    monkeypatch.setattr(auto_trader_module.ml_predictor, "predict", lambda df: None)

    monkeypatch.setattr(
        auto_trader_module.questrade, "refresh_access_token",
        lambda refresh_token: {
            "access_token": "access-2",
            "api_server": "https://api.questrade.com",
            "refresh_token": "refresh-2",
            "expires_in": 1800,
            "token_type": "Bearer",
        },
    )
    monkeypatch.setattr(auto_trader_module.questrade, "get_positions", lambda *a, **k: [])

    def fail_place_order(*args, **kwargs):
        raise AssertionError("should not place a live order without confirmation")

    monkeypatch.setattr(auto_trader_module.questrade, "place_order", fail_place_order)

    engine.update_config(models.AutoTraderConfigRequest(
        enabled=True, broker="questrade", symbols=["AAPL"], min_confidence=50, max_position_value=1000,
        confirmed_real_money=False, questrade_refresh_token="refresh-1", questrade_account_number="12345678",
    ))
    entries = engine.run_once()
    assert entries[0]["executed"] is False
    assert "DRY RUN" in entries[0]["reason"]


def test_run_once_respects_daily_trade_limit(engine, monkeypatch):
    monkeypatch.setattr(auto_trader_module, "get_market_session", lambda: MarketSession(status="open", now_et="x"))
    monkeypatch.setattr(auto_trader_module.yahoo, "get_history", lambda *a, **k: _trending_df())
    monkeypatch.setattr(
        auto_trader_module, "analyze",
        lambda symbol, df: SignalResult(symbol=symbol, action="STRONG_BUY", score=0.9, confidence=95, price=100.0, reasons=["strong uptrend"]),
    )
    monkeypatch.setattr(auto_trader_module.ml_predictor, "predict", lambda df: None)
    monkeypatch.setattr(auto_trader_module.alpaca, "get_positions", lambda *a, **k: [])
    monkeypatch.setattr(auto_trader_module.alpaca, "place_order", lambda *a, **k: {"id": "order-789"})

    engine.update_config(models.AutoTraderConfigRequest(
        enabled=True, symbols=["AAPL"], min_confidence=50, max_position_value=1000, max_daily_trades=0,
        environment="paper", alpaca_api_key_id="key", alpaca_api_secret_key="secret",
    ))
    entries = engine.run_once()
    assert entries[0]["executed"] is False
    assert "daily trade limit" in entries[0]["reason"]


def test_run_once_respects_max_open_positions(engine, monkeypatch):
    monkeypatch.setattr(auto_trader_module, "get_market_session", lambda: MarketSession(status="open", now_et="x"))
    monkeypatch.setattr(auto_trader_module.yahoo, "get_history", lambda *a, **k: _trending_df())
    monkeypatch.setattr(
        auto_trader_module, "analyze",
        lambda symbol, df: SignalResult(symbol=symbol, action="STRONG_BUY", score=0.9, confidence=95, price=100.0, reasons=["strong uptrend"]),
    )
    monkeypatch.setattr(auto_trader_module.ml_predictor, "predict", lambda df: None)
    # Already holding two unrelated positions; cap is 2, so a new buy is blocked.
    monkeypatch.setattr(
        auto_trader_module.alpaca, "get_positions",
        lambda *a, **k: [{"symbol": "MSFT", "qty": 1}, {"symbol": "NVDA", "qty": 1}],
    )
    monkeypatch.setattr(auto_trader_module.alpaca, "place_order", lambda *a, **k: {"id": "nope"})

    engine.update_config(models.AutoTraderConfigRequest(
        enabled=True, symbols=["AAPL"], min_confidence=50, max_position_value=1000,
        max_open_positions=2, environment="paper",
        alpaca_api_key_id="key", alpaca_api_secret_key="secret",
    ))
    entries = engine.run_once()
    assert entries[0]["executed"] is False
    assert "max open positions" in entries[0]["reason"]


def test_run_once_auto_select_trades_top_candidates(engine, monkeypatch):
    monkeypatch.setattr(auto_trader_module, "get_market_session", lambda: MarketSession(status="open", now_et="x"))
    monkeypatch.setattr(auto_trader_module, "DEFAULT_UNIVERSE", ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(auto_trader_module.yahoo, "get_history", lambda *a, **k: _trending_df())

    # AAA strongest, BBB next, CCC a HOLD that should never be traded.
    scores = {"AAA": 0.95, "BBB": 0.80, "CCC": 0.0}
    actions = {"AAA": "STRONG_BUY", "BBB": "BUY", "CCC": "HOLD"}
    monkeypatch.setattr(
        auto_trader_module, "analyze",
        lambda symbol, df: SignalResult(
            symbol=symbol, action=actions[symbol], score=scores[symbol],
            confidence=95 if actions[symbol] != "HOLD" else 10, price=100.0, reasons=["x"],
        ),
    )
    monkeypatch.setattr(auto_trader_module.ml_predictor, "predict", lambda df: None)
    monkeypatch.setattr(auto_trader_module.alpaca, "get_positions", lambda *a, **k: [])

    placed = []
    monkeypatch.setattr(
        auto_trader_module.alpaca, "place_order",
        lambda api_key, api_secret, symbol, qty, side, base_url=None: placed.append((symbol, side)) or {"id": symbol},
    )

    engine.update_config(models.AutoTraderConfigRequest(
        enabled=True, auto_select=True, auto_select_count=2, min_confidence=50,
        max_position_value=1000, max_daily_trades=10, environment="paper",
        alpaca_api_key_id="key", alpaca_api_secret_key="secret",
    ))
    entries = engine.run_once()

    traded = [e["symbol"] for e in entries if e["executed"]]
    assert traded == ["AAA", "BBB"]  # top 2 by score, CCC (HOLD) excluded
    assert ("AAA", "buy") in placed and ("BBB", "buy") in placed
