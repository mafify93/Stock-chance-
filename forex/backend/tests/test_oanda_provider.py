"""Unit tests for the OANDA provider's response parsing.

These mock the HTTP layer so no network or real credentials are needed - they
pin down how OANDA's v20 JSON shapes are turned into the app's data model.
"""
import httpx
import pytest

from app.cache import cache
from app.providers import oanda


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _mock_response(json_body, status=200):
    return httpx.Response(status, json=json_body, request=httpx.Request("GET", "http://test"))


def test_get_candles_parses_mid_ohlcv(monkeypatch):
    body = {
        "candles": [
            {"time": "2024-03-01T00:00:00.000000000Z", "complete": True,
             "volume": 100, "mid": {"o": "1.10000", "h": "1.10200", "l": "1.09900", "c": "1.10100"}},
            {"time": "2024-03-01T01:00:00.000000000Z", "complete": True,
             "volume": 150, "mid": {"o": "1.10100", "h": "1.10300", "l": "1.10050", "c": "1.10250"}},
            # Incomplete candle should be dropped.
            {"time": "2024-03-01T02:00:00.000000000Z", "complete": False,
             "volume": 5, "mid": {"o": "1.10250", "h": "1.10260", "l": "1.10240", "c": "1.10255"}},
        ]
    }
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _mock_response(body))

    df = oanda.get_candles("EUR_USD", "tok", "H1", 3)
    assert len(df) == 2
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df["Close"].iloc[-1] == pytest.approx(1.10250)
    assert df["Volume"].iloc[0] == 100


def test_get_pricing_computes_spread_in_pips(monkeypatch):
    body = {
        "prices": [
            {"instrument": "EUR_USD", "tradeable": True, "time": "t",
             "bids": [{"price": "1.10000"}], "asks": [{"price": "1.10012"}]},
        ]
    }
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _mock_response(body))

    pricing = oanda.get_pricing(["EUR_USD"], "tok", "acct")
    p = pricing["EUR_USD"]
    assert p["bid"] == pytest.approx(1.10000)
    assert p["ask"] == pytest.approx(1.10012)
    assert p["mid"] == pytest.approx(1.10006)
    assert p["spread_pips"] == pytest.approx(1.2, abs=0.05)  # 0.00012 / 0.0001


def test_error_response_raises_oanda_error(monkeypatch):
    monkeypatch.setattr(
        httpx, "request",
        lambda *a, **k: _mock_response({"errorMessage": "Insufficient authorization"}, status=401),
    )
    with pytest.raises(oanda.OandaError) as exc:
        oanda.get_candles("EUR_USD", "bad", "H1", 3)
    assert exc.value.status_code == 401
    assert "authorization" in str(exc.value).lower()


def test_place_market_order_builds_short_units(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _mock_response({"orderFillTransaction": {"id": "1", "units": "-1000", "price": "1.10000"}})

    monkeypatch.setattr(httpx, "request", fake_request)

    oanda.place_market_order("tok", "acct", "EUR_USD", -1000, stop_loss_price=1.10500)
    order = captured["json"]["order"]
    assert order["units"] == "-1000"
    assert order["instrument"] == "EUR_USD"
    assert order["type"] == "MARKET"
    assert order["stopLossOnFill"]["price"] == "1.10500"


def test_realized_pl_from_transactions_reads_closing_fill(monkeypatch):
    # Mirrors the real stream that broke the /trades lookup: trade 1307 opened
    # at txn 1307 and was closed by a stop-loss fill (1310) carrying the real
    # realizedPL in tradesClosed. The trades endpoint returned "does not exist";
    # this must still recover -494.94 from the transaction record.
    body = {
        "transactions": [
            {"id": "1308", "type": "TAKE_PROFIT_ORDER"},
            {"id": "1309", "type": "STOP_LOSS_ORDER"},
            {"id": "1310", "type": "ORDER_FILL", "reason": "STOP_LOSS_ORDER",
             "tradesClosed": [{"tradeID": "1307", "realizedPL": "-494.9441"}]},
        ]
    }
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _mock_response(body))
    pl = oanda.get_realized_pl_from_transactions("tok", "acct", "1307")
    assert pl == pytest.approx(-494.9441)


def test_realized_pl_from_transactions_none_when_not_closed_yet(monkeypatch):
    # No closing fill references this trade yet → None (must NOT be read as $0).
    body = {"transactions": [{"id": "1308", "type": "TAKE_PROFIT_ORDER"}]}
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _mock_response(body))
    assert oanda.get_realized_pl_from_transactions("tok", "acct", "1307") is None


def test_realized_pl_from_transactions_sums_partial_and_final(monkeypatch):
    # Partial close (tradeReduced) plus final close (tradesClosed) sum together.
    body = {
        "transactions": [
            {"id": "1311", "type": "ORDER_FILL", "reason": "MARKET_ORDER_TRADE_CLOSE",
             "tradeReduced": {"tradeID": "1307", "realizedPL": "100.0"}},
            {"id": "1312", "type": "ORDER_FILL", "reason": "STOP_LOSS_ORDER",
             "tradesClosed": [{"tradeID": "1307", "realizedPL": "-30.0"},
                              {"tradeID": "9999", "realizedPL": "500.0"}]},
        ]
    }
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _mock_response(body))
    # Only 1307's entries count (100 - 30 = 70); the unrelated 9999 is ignored.
    assert oanda.get_realized_pl_from_transactions("tok", "acct", "1307") == pytest.approx(70.0)
