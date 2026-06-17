from datetime import date

import pytest

from app import earnings_sentiment


class _Resp:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _claude_response(action="BUY", confidence=72, summary="Beat on revenue and EPS; guidance raised."):
    # Mimic an interleaved response: a tool-use block (web search) plus a text
    # block that wraps the JSON in some prose to exercise the {..} extraction.
    return {
        "content": [
            {"type": "server_tool_use", "name": "web_search"},
            {
                "type": "text",
                "text": (
                    "Based on my research, here is the assessment: "
                    f'{{"action": "{action}", "confidence": {confidence}, "summary": "{summary}"}}'
                ),
            },
        ]
    }


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(earnings_sentiment, "_cache", {})
    yield


def test_configured_false_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert earnings_sentiment.configured() is False


def test_configured_true_with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert earnings_sentiment.configured() is True


def test_get_sentiment_parses_json(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(
        earnings_sentiment.httpx, "post", lambda *a, **k: _Resp(_claude_response("SELL", 40, "Missed guidance."))
    )
    result = earnings_sentiment.get_sentiment("AAPL")
    assert result is not None
    assert result["action"] == "SELL"
    assert result["confidence"] == 40.0
    assert "guidance" in result["summary"].lower()
    assert result["model"]


def test_get_sentiment_none_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert earnings_sentiment.get_sentiment("AAPL") is None


def test_get_sentiment_none_on_failure(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    def boom(*a, **k):
        raise RuntimeError("api down")

    monkeypatch.setattr(earnings_sentiment.httpx, "post", boom)
    assert earnings_sentiment.get_sentiment("AAPL") is None


def test_cache_prevents_second_post(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    calls = {"n": 0}

    def counting_post(*a, **k):
        calls["n"] += 1
        return _Resp(_claude_response())

    monkeypatch.setattr(earnings_sentiment.httpx, "post", counting_post)

    first = earnings_sentiment.get_sentiment("AAPL")
    second = earnings_sentiment.get_sentiment("AAPL")
    assert calls["n"] == 1  # second served from (symbol, today) cache
    assert second == first
