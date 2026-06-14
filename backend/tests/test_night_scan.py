import json
from datetime import datetime

from app import night_scan as night_scan_module
from app.night_scan import NightScanEngine, _extract_json, _is_scan_time
from app.intraday import ET


def _engine(tmp_path, monkeypatch):
    monkeypatch.setattr(night_scan_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(night_scan_module, "RESULT_PATH", tmp_path / "night_scan.json")
    return NightScanEngine()


def _fake_response(payload: dict):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "content": [
                    {"type": "server_tool_use", "id": "x", "name": "web_search", "input": {"query": "AAPL news"}},
                    {"type": "web_search_tool_result", "tool_use_id": "x", "content": []},
                    {"type": "text", "text": json.dumps(payload)},
                ]
            }

    return FakeResponse()


def test_not_configured_without_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine = _engine(tmp_path, monkeypatch)
    assert engine.run_once() is None
    status = engine.get_status()
    assert status.configured is False
    assert status.result is None


def test_run_once_parses_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    engine = _engine(tmp_path, monkeypatch)

    payload = {
        "summary": "Quiet evening overall, a couple of earnings-driven setups.",
        "picks": [
            {"symbol": "aapl", "action": "buy", "confidence": 80, "catalyst": "Beat earnings yesterday.", "plan": "Consider buying near the open."},
            {"symbol": "tsla", "action": "watch", "confidence": 55, "catalyst": "Mixed delivery numbers.", "plan": "Wait for confirmation."},
            {"symbol": "xyz", "action": "sell", "confidence": 90, "catalyst": "invalid action, should be dropped", "plan": "n/a"},
        ],
    }
    monkeypatch.setattr(night_scan_module.httpx, "post", lambda *a, **k: _fake_response(payload))

    result = engine.run_once()
    assert result is not None
    assert result.summary.startswith("Quiet evening")
    assert [p.symbol for p in result.picks] == ["AAPL", "TSLA"]
    assert result.picks[0].action == "BUY"
    assert result.picks[1].action == "WATCH"

    result_path = night_scan_module.RESULT_PATH
    assert result_path.exists()
    on_disk = json.loads(result_path.read_text())
    assert on_disk["picks"][0]["symbol"] == "AAPL"

    # Reloading should pick up the persisted result.
    reloaded = NightScanEngine()
    status = reloaded.get_status()
    assert status.result is not None
    assert status.result.picks[0].symbol == "AAPL"


def test_run_once_handles_request_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    engine = _engine(tmp_path, monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(night_scan_module.httpx, "post", boom)
    assert engine.run_once() is None
    assert engine.get_status().result is None


def test_extract_json_strips_surrounding_text():
    text = 'Sure, here you go:\n{"summary": "ok", "picks": []}\nLet me know if you need more.'
    assert json.loads(_extract_json(text)) == {"summary": "ok", "picks": []}


def test_is_scan_time():
    # Sunday 8 PM ET - scan time.
    sunday_8pm = datetime(2026, 6, 14, 20, 0, tzinfo=ET)
    assert sunday_8pm.weekday() == 6
    assert _is_scan_time(sunday_8pm) is True

    # Sunday 7:59 PM ET - too early.
    sunday_before = datetime(2026, 6, 14, 19, 59, tzinfo=ET)
    assert _is_scan_time(sunday_before) is False

    # Friday 9 PM ET - tomorrow is Saturday, no scan.
    friday_9pm = datetime(2026, 6, 19, 21, 0, tzinfo=ET)
    assert friday_9pm.weekday() == 4
    assert _is_scan_time(friday_9pm) is False


def test_next_run_at_skips_to_next_scan_weekday():
    # Friday 9 PM ET -> next scan is Sunday 8 PM ET.
    friday_9pm = datetime(2026, 6, 19, 21, 0, tzinfo=ET)
    next_run = NightScanEngine._next_run_at(friday_9pm)
    assert next_run.weekday() == 6  # Sunday
    assert next_run.hour == night_scan_module.SCAN_HOUR_ET
    assert next_run.date() > friday_9pm.date()

    # Sunday 7 PM ET -> next scan is later that same evening.
    sunday_7pm = datetime(2026, 6, 14, 19, 0, tzinfo=ET)
    next_run = NightScanEngine._next_run_at(sunday_7pm)
    assert next_run.date() == sunday_7pm.date()
    assert next_run.hour == night_scan_module.SCAN_HOUR_ET
