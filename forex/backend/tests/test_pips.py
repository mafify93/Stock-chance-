import pytest

from app import pips


def test_normalize_accepts_many_forms():
    assert pips.normalize("eur/usd") == "EUR_USD"
    assert pips.normalize("EURUSD") == "EUR_USD"
    assert pips.normalize("gbp-jpy") == "GBP_JPY"
    assert pips.normalize("USD_CHF") == "USD_CHF"


def test_display():
    assert pips.display("EUR_USD") == "EUR/USD"
    assert pips.display("usdjpy") == "USD/JPY"


def test_pip_size_jpy_vs_standard():
    assert pips.pip_size("EUR_USD") == 0.0001
    assert pips.pip_size("USD_JPY") == 0.01
    assert pips.pip_size("GBP_JPY") == 0.01


def test_price_decimals():
    assert pips.price_decimals("EUR_USD") == 5
    assert pips.price_decimals("USD_JPY") == 3


def test_to_and_from_pips_roundtrip():
    # 20 pips on EUR/USD == 0.0020
    assert pips.from_pips("EUR_USD", 20) == pytest.approx(0.0020)
    assert pips.to_pips("EUR_USD", 0.0020) == pytest.approx(20)
    # JPY pairs: 20 pips == 0.20
    assert pips.from_pips("USD_JPY", 20) == pytest.approx(0.20)
    assert pips.to_pips("USD_JPY", 0.20) == pytest.approx(20)


def test_base_and_quote():
    assert pips.base_currency("EUR_USD") == "EUR"
    assert pips.quote_currency("EUR_USD") == "USD"
