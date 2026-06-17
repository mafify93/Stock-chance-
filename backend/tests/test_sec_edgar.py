import json
from datetime import date, timedelta

import pytest

from app.providers import sec_edgar


_COMPANY_TICKERS = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
}


def _form4_xml(code: str, shares: float) -> str:
    return f"""<?xml version="1.0"?>
<ownershipDocument>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionCoding>
        <transactionCode>{code}</transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares>
          <value>{shares}</value>
        </transactionShares>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


class _Resp:
    def __init__(self, *, json_data=None, text=None, status_code=200):
        self._json = json_data
        self.text = text or ""
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def _reset_caches(monkeypatch):
    # Isolate module-level caches between tests.
    monkeypatch.setattr(sec_edgar, "_ticker_map", None)
    monkeypatch.setattr(sec_edgar, "_signal_cache", {})
    # Avoid real sleeps.
    monkeypatch.setattr(sec_edgar.time, "sleep", lambda *_a, **_k: None)
    yield


def _submissions(forms, dates, accessions, docs):
    return {
        "filings": {
            "recent": {
                "form": forms,
                "filingDate": dates,
                "accessionNumber": accessions,
                "primaryDocument": docs,
            }
        }
    }


def test_get_insider_signal_net_buy(monkeypatch):
    today = date.today().isoformat()
    subs = _submissions(
        forms=["4", "4", "10-K"],
        dates=[today, today, today],
        accessions=["0000320193-24-000001", "0000320193-24-000002", "0000320193-24-000003"],
        docs=["a.xml", "b.xml", "c.htm"],
    )

    def fake_get(url, **kwargs):
        if "company_tickers" in url:
            return _Resp(json_data=_COMPANY_TICKERS)
        if "submissions" in url:
            return _Resp(json_data=subs)
        if url.endswith("a.xml"):
            return _Resp(text=_form4_xml("P", 1000))  # bought
        if url.endswith("b.xml"):
            return _Resp(text=_form4_xml("S", 200))  # sold
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(sec_edgar.httpx, "get", fake_get)

    result = sec_edgar.get_insider_signal("AAPL")
    assert result is not None
    assert result["action"] == "BUY"
    assert result["buys"] == 1
    assert result["sells"] == 1
    assert result["net_shares"] == 800
    # net 800 / total 1200 * 100 = 66.7
    assert result["confidence"] == pytest.approx(66.7, abs=0.1)


def test_get_insider_signal_net_sell(monkeypatch):
    today = date.today().isoformat()
    subs = _submissions(
        forms=["4", "4"],
        dates=[today, today],
        accessions=["0000320193-24-000001", "0000320193-24-000002"],
        docs=["a.xml", "b.xml"],
    )

    def fake_get(url, **kwargs):
        if "company_tickers" in url:
            return _Resp(json_data=_COMPANY_TICKERS)
        if "submissions" in url:
            return _Resp(json_data=subs)
        if url.endswith("a.xml"):
            return _Resp(text=_form4_xml("P", 100))
        if url.endswith("b.xml"):
            return _Resp(text=_form4_xml("S", 900))
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(sec_edgar.httpx, "get", fake_get)

    result = sec_edgar.get_insider_signal("AAPL")
    assert result is not None
    assert result["action"] == "SELL"
    assert result["net_shares"] == -800


def test_unknown_ticker_returns_none(monkeypatch):
    def fake_get(url, **kwargs):
        if "company_tickers" in url:
            return _Resp(json_data=_COMPANY_TICKERS)
        raise AssertionError("should not reach submissions for unknown ticker")

    monkeypatch.setattr(sec_edgar.httpx, "get", fake_get)
    assert sec_edgar.get_insider_signal("NOPE") is None


def test_no_recent_form4_returns_none(monkeypatch):
    old = (date.today() - timedelta(days=400)).isoformat()
    subs = _submissions(
        forms=["4"],
        dates=[old],  # outside the lookback window
        accessions=["0000320193-24-000001"],
        docs=["a.xml"],
    )

    def fake_get(url, **kwargs):
        if "company_tickers" in url:
            return _Resp(json_data=_COMPANY_TICKERS)
        if "submissions" in url:
            return _Resp(json_data=subs)
        raise AssertionError("should not fetch the out-of-window filing")

    monkeypatch.setattr(sec_edgar.httpx, "get", fake_get)
    assert sec_edgar.get_insider_signal("AAPL") is None


def test_network_failure_returns_none(monkeypatch):
    def fake_get(url, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(sec_edgar.httpx, "get", fake_get)
    assert sec_edgar.get_insider_signal("AAPL") is None


def test_daily_cache_short_circuits_second_call(monkeypatch):
    today = date.today().isoformat()
    subs = _submissions(
        forms=["4"],
        dates=[today],
        accessions=["0000320193-24-000001"],
        docs=["a.xml"],
    )
    calls = {"n": 0}

    def fake_get(url, **kwargs):
        calls["n"] += 1
        if "company_tickers" in url:
            return _Resp(json_data=_COMPANY_TICKERS)
        if "submissions" in url:
            return _Resp(json_data=subs)
        if url.endswith("a.xml"):
            return _Resp(text=_form4_xml("P", 500))
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(sec_edgar.httpx, "get", fake_get)

    first = sec_edgar.get_insider_signal("AAPL")
    calls_after_first = calls["n"]
    assert calls_after_first > 0
    second = sec_edgar.get_insider_signal("AAPL")
    # Second call served from the (symbol, today) cache - no new HTTP calls.
    assert calls["n"] == calls_after_first
    assert second == first
