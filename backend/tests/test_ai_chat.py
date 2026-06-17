from app import ai_chat, models


def _fake_response(text: str):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"content": [{"type": "text", "text": text}]}

    return FakeResponse()


def test_not_configured_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ai_chat.configured() is False
    assert ai_chat.chat([models.ChatMessage(role="user", content="hi")], models.AIChatContext()) is None


def test_chat_includes_context_and_returns_reply(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        ai_chat.ai_context,
        "symbol_snapshot",
        lambda sym: {"symbol": sym, "price": 100.0, "signal": "BUY", "confidence": 70.0, "reasons": ["uptrend"], "ml_probability_up": 0.6},
    )
    monkeypatch.setattr(ai_chat.ai_context, "auto_trader_summary", lambda **k: {"enabled": True, "recent_decisions": []})

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["payload"] = json
        return _fake_response("Your AAPL position looks healthy given the BUY signal.")

    monkeypatch.setattr(ai_chat.httpx, "post", fake_post)

    context = models.AIChatContext(
        positions=[models.ChatPosition(symbol="aapl", quantity=2, avg_entry_price=150.0)],
        watchlist=["tsla"],
    )
    messages = [models.ChatMessage(role="user", content="How's my AAPL position?")]

    reply = ai_chat.chat(messages, context)
    assert reply == "Your AAPL position looks healthy given the BUY signal."

    payload = captured["payload"]
    context_message = payload["messages"][0]["content"]
    assert "AAPL" in context_message
    assert "TSLA" in context_message
    assert payload["messages"][-1]["content"] == "How's my AAPL position?"


def test_chat_handles_request_failure(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(ai_chat.ai_context, "symbol_snapshot", lambda sym: None)
    monkeypatch.setattr(ai_chat.ai_context, "auto_trader_summary", lambda **k: {"enabled": False, "recent_decisions": []})

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(ai_chat.httpx, "post", boom)
    reply = ai_chat.chat([models.ChatMessage(role="user", content="hi")], models.AIChatContext())
    assert reply is None


def test_chat_returns_none_on_empty_reply(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(ai_chat.ai_context, "symbol_snapshot", lambda sym: None)
    monkeypatch.setattr(ai_chat.ai_context, "auto_trader_summary", lambda **k: {"enabled": False, "recent_decisions": []})
    monkeypatch.setattr(ai_chat.httpx, "post", lambda *a, **k: _fake_response("   "))

    reply = ai_chat.chat([models.ChatMessage(role="user", content="hi")], models.AIChatContext())
    assert reply is None
