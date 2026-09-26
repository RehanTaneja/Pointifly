"""Visa Foreign Exchange Rates (card rates, rateProductCode "A").

Rate limits: at most one API call per currency pair per UTC day. Rates are cached in
app/data/visa_fx_rates.json (committed, so the demo works offline); if Visa is unreachable
the last cached rate is used and its date is shown.
Docs: https://developer.visa.com/capabilities/foreign_exchange/reference
"""

import json
from datetime import datetime, timezone
from decimal import Decimal

from ..data_store import DATA_DIR
from . import client

CACHE_PATH = DATA_DIR / "visa_fx_rates.json"
SOURCE = "Visa FX rate"

# ISO 4217 alphabetic -> numeric (the API takes numeric codes).
ISO_NUMERIC = {
    "USD": "840", "CAD": "124", "MXN": "484", "EUR": "978", "GBP": "826", "CHF": "756", "JPY": "392",
    "INR": "356", "CNY": "156", "KRW": "410", "HKD": "344", "SGD": "702", "THB": "764", "AUD": "036",
    "NZD": "554", "AED": "784", "BRL": "986", "TRY": "949",
}

# Country (ISO 3166 alpha-2) -> currency, for the destinations we show a local rate for.
EURO_AREA = ["AT", "BE", "HR", "CY", "EE", "FI", "FR", "DE", "GR", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PT", "SK", "SI", "ES"]
COUNTRY_CURRENCY = {
    "US": "USD", "CA": "CAD", "MX": "MXN", "GB": "GBP", "CH": "CHF", "JP": "JPY", "IN": "INR", "CN": "CNY",
    "KR": "KRW", "HK": "HKD", "SG": "SGD", "TH": "THB", "AU": "AUD", "NZ": "NZD", "AE": "AED", "BR": "BRL",
    "TR": "TRY", **{c: "EUR" for c in EURO_AREA},
}


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _read_cache() -> dict:
    return json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}


def _write_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")


def fetch_rate(src: str, dst: str) -> Decimal:
    """One API call: Visa's card conversion rate from src to dst (excludes markup)."""
    r = client.call(
        "POST",
        "/forexrates/v2/foreignexchangerates",
        {
            "sourceCurrencyCode": ISO_NUMERIC[src],
            "destinationCurrencyCode": ISO_NUMERIC[dst],
            "sourceAmount": "100.00",
            "rateProductCode": "A",
            "markupRate": "0.00",
        },
    )
    return Decimal(r["conversionRate"])


def rate(src: str, dst: str) -> dict | None:
    """{rate, date, source} for 1 src in dst, or None. Cached per pair per day."""
    if src == dst:
        return {"rate": 1.0, "date": _today(), "source": SOURCE}
    if src not in ISO_NUMERIC or dst not in ISO_NUMERIC:
        return None
    key = f"{src}->{dst}"
    cache = _read_cache()
    cached = cache.get(key)
    if cached and cached["date"] == _today():
        return cached
    if client.configured():
        try:
            value = fetch_rate(src, dst)
            cache[key] = {"rate": float(value), "date": _today(), "source": SOURCE}
            _write_cache(cache)
            return cache[key]
        except (client.VisaError, OSError, KeyError, ValueError):
            pass
    return cached  # last known rate (its date says how old), or None


def convert(amount: float, src: str, dst: str) -> dict | None:
    """{amount, rate, date, source} converted at Visa's rate, or None if no rate is available."""
    r = rate(src, dst)
    if r is None:
        return None
    return {**r, "amount": round(amount * r["rate"], 2)}
