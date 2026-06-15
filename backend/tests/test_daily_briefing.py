import json

from app import daily_briefing, models


def _fake_response(payload: dict):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"content": [{"type": "text", "text": json.dumps(payload)}]}

    return FakeResponse()


def test_not_configured_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert daily_briefing.configured() is False
    assert daily_briefing.generate(models.DailyBriefingRequest()) is None


def test_generate_returns_briefing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        daily_briefing.ai_context,
        "symbol_snapshot",
        lambda sym: {"symbol": sym, "price": 100.0, "signal": "BUY", "confidence": 70.0, "reasons": ["uptrend"], "ml_probability_up": 0.6},
    )
    monkeypatch.setattr(daily_briefing.ai_context, "auto_trader_summary", lambda **k: {"enabled": True, "recent_decisions": []})
    monkeypatch.setattr(daily_briefing.night_scan, "get_status", lambda: models.NightScanStatus(configured=True, result=None))

    payload = {"briefing": "Your AAPL position is up slightly; the BUY signal remains intact heading into the open."}
    monkeypatch.setattr(daily_briefing.httpx, "post", lambda *a, **k: _fake_response(payload))

    request = models.DailyBriefingRequest(
        positions=[models.ChatPosition(symbol="aapl", quantity=2, avg_entry_price=150.0)],
        watchlist=["tsla"],
    )
    result = daily_briefing.generate(request)
    assert result is not None
    assert result.briefing.startswith("Your AAPL position")
    assert result.model


def test_generate_handles_request_failure(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(daily_briefing.ai_context, "symbol_snapshot", lambda sym: None)
    monkeypatch.setattr(daily_briefing.ai_context, "auto_trader_summary", lambda **k: {"enabled": False, "recent_decisions": []})
    monkeypatch.setattr(daily_briefing.night_scan, "get_status", lambda: models.NightScanStatus(configured=False, result=None))

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(daily_briefing.httpx, "post", boom)
    result = daily_briefing.generate(models.DailyBriefingRequest())
    assert result is None


def test_generate_handles_invalid_json(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(daily_briefing.ai_context, "symbol_snapshot", lambda sym: None)
    monkeypatch.setattr(daily_briefing.ai_context, "auto_trader_summary", lambda **k: {"enabled": False, "recent_decisions": []})
    monkeypatch.setattr(daily_briefing.night_scan, "get_status", lambda: models.NightScanStatus(configured=False, result=None))

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"content": [{"type": "text", "text": "not json"}]}

    monkeypatch.setattr(daily_briefing.httpx, "post", lambda *a, **k: FakeResponse())
    assert daily_briefing.generate(models.DailyBriefingRequest()) is None
