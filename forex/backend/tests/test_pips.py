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


def test_pip_size_gold_matches_oanda_pip_location():
    # OANDA's XAU_USD pipLocation is -2 (same numeric convention as JPY
    # pairs), confirmed via /oanda-debug?instrument=XAU_USD, not assumed.
    assert pips.pip_size("XAU_USD") == 0.01
    assert pips.price_decimals("XAU_USD") == 3


def test_pip_value_gold_is_direct_no_conversion_needed():
    # XAU/USD is USD-quoted, so pip value is exactly pip_size regardless of
    # gold's much larger absolute price — no cross-rate conversion needed.
    assert pips.pip_value_per_unit("XAU_USD", 4008.05) == pytest.approx(0.01)
    assert pips.pip_value_per_unit("XAU_USD", 4008.05, 1.0) == pytest.approx(0.01)


def test_calculate_units_gold_realistic_stop():
    from app.autotrader.risk import calculate_units

    # $85k account, 3% risk, $15 stop (1500 pips at gold's 0.01 pip size).
    units = calculate_units(85_000, 0.03, 1500, "XAU_USD", 4008.05, 1.0)
    actual_risk = units * 1500 * 0.01
    assert actual_risk == pytest.approx(2550, rel=0.01)


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


def test_pip_value_usd_quoted_pairs():
    # USD-quoted: pip value is exactly pip_size, regardless of conversion.
    assert pips.pip_value_per_unit("EUR_USD", 1.10) == pytest.approx(0.0001)
    assert pips.pip_value_per_unit("EUR_USD", 1.10, 1.0) == pytest.approx(0.0001)


def test_pip_value_cross_pair_uses_quote_conversion():
    # EUR/JPY: real USD pip value = 0.01 / USDJPY. With quote_to_usd supplied
    # it must be exact — NOT the raw 0.01 (the bug that under-sized ~145x).
    usdjpy = 145.0
    qtu = 1.0 / usdjpy
    assert pips.pip_value_per_unit("EUR_JPY", 161.0, qtu) == pytest.approx(0.01 / usdjpy)
    # Legacy path (no conversion) returns the raw quote-ccy pip size.
    assert pips.pip_value_per_unit("EUR_JPY", 161.0) == pytest.approx(0.01)


def test_calculate_units_risks_correct_amount_on_cross():
    from app.autotrader.risk import calculate_units

    usdjpy = 145.0
    qtu = 1.0 / usdjpy
    # $100k account, 1% risk, 15-pip stop on EUR/JPY.
    units = calculate_units(100_000, 0.01, 15, "EUR_JPY", 161.0, qtu)
    # Actual USD risk = units * stop_pips * pip_size / USDJPY should equal ~ $1,000.
    actual_risk = units * 15 * 0.01 / usdjpy
    assert actual_risk == pytest.approx(1000, rel=0.01)
