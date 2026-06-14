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
    assert config.environment == "paper"
    assert config.confirmed_real_money is False
    assert config.alpaca_configured is False


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
