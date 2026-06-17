"""Insider-trading signal from SEC EDGAR Form 4 filings (free, no API key).

Company insiders (officers, directors, 10%+ owners) must report their trades
on Form 4 within two business days. Open-market purchases (transaction code
"P") are a well-studied bullish signal; sales (code "S") are weaker but
informative. This module aggregates recent Form 4 activity for a symbol into
a single BUY/SELL/HOLD vote with a conviction-scaled confidence, suitable for
feeding into `app.ai_combine.combine` as an auxiliary factor.

Everything here is best-effort: any network/parse/rate-limit failure returns
None (no vote) rather than raising. Results are cached per (symbol, day) to
avoid refetching, and SEC's fair-access policy is respected with a descriptive
User-Agent and small inter-request delays.
"""
from __future__ import annotations

import logging
import os
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = os.environ.get("SEC_EDGAR_USER_AGENT", "StockChance research contact@stockchance.app")
_HEADERS = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}/{doc}"

_MAX_FORM4 = 40  # cap how many Form-4 docs we fetch per symbol per day
_TIMEOUT = 15
_REQUEST_DELAY = 0.1  # seconds between SEC requests

# Module-level caches living for the process lifetime.
_ticker_map: dict[str, str] | None = None  # uppercased ticker -> 10-digit CIK
_signal_cache: dict[tuple[str, date], dict | None] = {}


def _ticker_to_cik(symbol: str) -> str | None:
    """Map an uppercased ticker to its 10-digit zero-padded CIK string, or
    None if not found. The ticker->CIK table is cached for the process."""
    global _ticker_map
    if _ticker_map is None:
        resp = httpx.get(COMPANY_TICKERS_URL, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        mapping: dict[str, str] = {}
        for entry in data.values():
            ticker = str(entry.get("ticker", "")).upper()
            cik = entry.get("cik_str")
            if ticker and cik is not None:
                mapping[ticker] = str(int(cik)).zfill(10)
        _ticker_map = mapping
        time.sleep(_REQUEST_DELAY)

    return _ticker_map.get(symbol.upper())


def _local_name(tag: str) -> str:
    """Strip any XML namespace from a tag name."""
    return tag.rsplit("}", 1)[-1]


def _find_local(elem: ET.Element, name: str) -> ET.Element | None:
    for child in elem.iter():
        if _local_name(child.tag) == name:
            return child
    return None


def _parse_form4_transactions(xml_text: str) -> tuple[float, float, int, int]:
    """Parse a Form 4 XML document; return (shares_bought, shares_sold,
    buy_txn_count, sell_txn_count) over non-derivative transactions."""
    root = ET.fromstring(xml_text)
    bought = sold = 0.0
    buys = sells = 0
    for elem in root.iter():
        if _local_name(elem.tag) != "nonDerivativeTransaction":
            continue
        coding = _find_local(elem, "transactionCoding")
        code_elem = _find_local(coding, "transactionCode") if coding is not None else None
        code = (code_elem.text or "").strip().upper() if code_elem is not None and code_elem.text else ""

        amounts = _find_local(elem, "transactionAmounts")
        shares_elem = _find_local(amounts, "transactionShares") if amounts is not None else None
        value_elem = _find_local(shares_elem, "value") if shares_elem is not None else None
        if value_elem is None or value_elem.text is None:
            continue
        try:
            shares = float(value_elem.text.strip())
        except ValueError:
            continue

        if code == "P":
            bought += shares
            buys += 1
        elif code == "S":
            sold += shares
            sells += 1
    return bought, sold, buys, sells


def get_insider_signal(symbol: str, lookback_days: int = 90) -> dict | None:
    """Aggregate recent Form 4 insider activity into a BUY/SELL/HOLD vote.

    Returns a dict with `action`, `confidence` (0-100, scaled by net
    conviction), `buys`, `sells`, `net_shares`, and a plain-English
    `summary` - or None if there is no Form-4 activity in the window or any
    failure occurs."""
    cache_key = (symbol.upper(), date.today())
    if cache_key in _signal_cache:
        return _signal_cache[cache_key]

    try:
        result = _compute_insider_signal(symbol, lookback_days)
        _signal_cache[cache_key] = result
        return result
    except Exception:  # noqa: BLE001 - insider signal is best-effort/optional
        logger.exception("Insider signal request failed for %s", symbol)
        return None


def _compute_insider_signal(symbol: str, lookback_days: int) -> dict | None:
    cik = _ticker_to_cik(symbol)
    if cik is None:
        return None

    resp = httpx.get(SUBMISSIONS_URL.format(cik=cik), headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    time.sleep(_REQUEST_DELAY)
    recent = resp.json().get("filings", {}).get("recent", {})

    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    filing_dates = recent.get("filingDate", [])

    cutoff = date.today() - timedelta(days=lookback_days)
    cik_int = int(cik)

    total_bought = total_sold = 0.0
    total_buys = total_sells = 0
    processed = 0

    for form, accession, doc, filing_date in zip(forms, accessions, primary_docs, filing_dates):
        if form != "4":
            continue
        try:
            filed = datetime.strptime(filing_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if filed < cutoff:
            continue
        if processed >= _MAX_FORM4:
            break
        if not accession or not doc:
            continue

        accession_no_dashes = accession.replace("-", "")
        url = ARCHIVES_URL.format(cik_int=cik_int, accession=accession_no_dashes, doc=doc)
        doc_resp = httpx.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        time.sleep(_REQUEST_DELAY)
        if doc_resp.status_code != 200:
            continue
        bought, sold, buys, sells = _parse_form4_transactions(doc_resp.text)
        total_bought += bought
        total_sold += sold
        total_buys += buys
        total_sells += sells
        processed += 1

    if processed == 0:
        return None  # no Form-4 in window -> no signal, don't vote

    net = total_bought - total_sold
    total = total_bought + total_sold
    confidence = round(min(100.0, abs(net) / total * 100), 1) if total > 0 else 0.0

    if net > 0:
        action = "BUY"
    elif net < 0:
        action = "SELL"
    else:
        action = "HOLD"

    summary = (
        f"Insiders bought {total_bought:,.0f} and sold {total_sold:,.0f} shares "
        f"across {total_buys} purchase and {total_sells} sale transactions in the "
        f"last {lookback_days} days (net {net:+,.0f} shares)."
    )

    return {
        "action": action,
        "confidence": confidence,
        "buys": total_buys,
        "sells": total_sells,
        "net_shares": net,
        "summary": summary,
    }
