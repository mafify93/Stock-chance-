from app import ai_analyst


def test_not_configured_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ai_analyst.configured() is False
    assert ai_analyst.analyze("AAPL", {"action": "BUY", "score": 0.5, "confidence": 60, "price": 100, "reasons": []}, None) is None


def test_configured_with_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert ai_analyst.configured() is True


def test_analyze_handles_request_failure(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(ai_analyst.httpx, "post", boom)
    result = ai_analyst.analyze("AAPL", {"action": "BUY", "score": 0.5, "confidence": 60, "price": 100, "reasons": []}, None)
    assert result is None
