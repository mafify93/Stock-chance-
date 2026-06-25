"""Tests for encrypted bot-state persistence and auto-resume."""
from datetime import date

import pytest

from app.autotrader import persistence
from app.autotrader.state import TradeRecord, bot_state


@pytest.fixture(autouse=True)
def _isolated_state_dir(tmp_path, monkeypatch):
    """Point persistence at a temp dir and a fixed key; restore bot_state after."""
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.setenv("STATE_KEY", "unit-test-key")
    # Snapshot the singleton so the test can mutate it freely.
    saved = {
        "running": bot_state.running, "token": bot_state.token,
        "account_id": bot_state.account_id, "environment": bot_state.environment,
        "trades": list(bot_state.trades), "daily_pl": bot_state.daily_pl,
        "halted": bot_state.halted, "session_date": bot_state.session_date,
        "trades_today": bot_state.trades_today,
    }
    yield
    for k, v in saved.items():
        setattr(bot_state, k, v)


def test_round_trip_restores_running_and_credentials():
    bot_state.running = True
    bot_state.token = "secret-token-123"
    bot_state.account_id = "101-001-999"
    bot_state.environment = "practice"
    bot_state.daily_pl = -12.5
    bot_state.trades_today = 3
    bot_state.session_date = date(2026, 6, 19)
    bot_state.trades = [
        TradeRecord(pair="EUR_USD", side="long", units=1000, entry=1.08,
                    stop=1.078, target=1.084, opened_at="2026-06-19T10:00:00",
                    trade_id="T1", status="open"),
    ]

    persistence.save_state()

    # Wipe in-memory state as a restart would.
    bot_state.running = False
    bot_state.token = ""
    bot_state.account_id = ""
    bot_state.daily_pl = 0.0
    bot_state.trades = []
    bot_state.session_date = None

    was_running = persistence.load_into_state()

    assert was_running is True
    assert bot_state.running is True
    assert bot_state.token == "secret-token-123"
    assert bot_state.account_id == "101-001-999"
    assert bot_state.daily_pl == -12.5
    assert bot_state.trades_today == 3
    assert bot_state.session_date == date(2026, 6, 19)
    assert len(bot_state.trades) == 1
    assert bot_state.trades[0].trade_id == "T1"


def test_token_is_encrypted_on_disk():
    bot_state.token = "plaintext-should-not-appear"
    persistence.save_state()
    with open(persistence._state_file(), "rb") as fh:
        raw = fh.read()
    assert b"plaintext-should-not-appear" not in raw


def test_stopped_bot_does_not_report_running():
    bot_state.running = False
    bot_state.token = "tok"
    bot_state.account_id = "acc"
    persistence.save_state()
    bot_state.running = True  # pretend something flipped it
    assert persistence.load_into_state() is False
    assert bot_state.running is False


def test_load_with_no_saved_file_is_false(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "empty"))
    assert persistence.load_into_state() is False
