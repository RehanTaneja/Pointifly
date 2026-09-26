"""Visa Merchant Offers Resource Center (VMORC): travel card benefits for the dashboard.

Display only; offers are card-program benefits, not flight prices, so they don't enter the
optimizer. Rate limits: at most one API call per UTC day; results are cached (filtered and
normalized) in app/data/visa_offers.json. The Sandbox catalog mixes real-looking offers with
placeholder records, which are filtered out.
Docs: https://developer.visa.com/capabilities/vmorc/reference
"""

import html
import json
import re
from datetime import datetime, timezone

from ..data_store import DATA_DIR
from . import client

CACHE_PATH = DATA_DIR / "visa_offers.json"
TRAVEL_CATEGORY_KEY = 18
PLACEHOLDER = re.compile(
    r"\btest\b|lorem|ipsum|sample|shirley|merchant (one|two)|convallis|^\d{8}|placeholder|click me", re.I
)
TRAVEL_WORDS = re.compile(r"airline|flight|hotel|resort|travel|trip|lounge|luggage|baggage", re.I)
HREF = re.compile(r'href="([^"]+)"')


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _text(o: dict, field: str) -> str:
    value = o.get(field) or ""
    if isinstance(value, dict):
        value = value.get("text") or ""
    return html.unescape(str(value)).strip()


def _link(raw: str) -> str | None:
    raw = html.unescape(raw or "")
    m = HREF.search(raw)
    url = m.group(1) if m else raw.strip()
    return url if url.startswith("https://") else None


def travel_offers(raw_offers: list[dict], country: str = "United States of America") -> list[dict]:
    """Real (non-placeholder) travel offers redeemable in `country`, normalized for the UI."""
    out = []
    for o in raw_offers:
        merchants = [html.unescape(m.get("merchant", "")) for m in o.get("merchantList") or []]
        blob = " ".join([_text(o, "offerTitle"), _text(o, "offerShortDescription"), *merchants])
        travel = TRAVEL_WORDS.search(blob) or any(
            c.get("key") == TRAVEL_CATEGORY_KEY for c in o.get("categorySubcategoryList") or []
        )
        countries = [c.get("value") for c in o.get("redemptionCountries") or []]
        if PLACEHOLDER.search(blob) or not travel or country not in countries:
            continue
        images = [i.get("fileLocation") for i in o.get("imageList") or [] if i.get("fileLocation", "").startswith("https://")]
        out.append(
            {
                "id": o.get("offerId"),
                "title": _text(o, "offerTitle"),
                "description": _text(o, "offerShortDescription"),
                "merchant": ", ".join(merchants),
                "cards": [c.get("value") for c in o.get("cardProductList") or []],
                "valid_to": o.get("validityToDate"),
                "url": _link(o.get("redemptionUrl") or ""),
                "image": images[0] if images else None,
            }
        )
    return out


def get_travel_offers() -> dict:
    """{offers, date, source}. At most one VMORC call per day; falls back to the cached list."""
    cached = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else None
    if cached and cached["date"] == _today():
        return cached
    if client.configured():
        try:
            raw = client.call("GET", "/vmorc/offers/v1/all").get("Offers", [])
            fresh = {"offers": travel_offers(raw), "date": _today(), "source": "Visa Merchant Offers Resource Center"}
            CACHE_PATH.write_text(json.dumps(fresh, indent=2, ensure_ascii=False) + "\n")
            return fresh
        except (client.VisaError, OSError, ValueError):
            pass
    return cached or {"offers": [], "date": None, "source": "Visa Merchant Offers Resource Center"}
