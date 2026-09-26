"""Builds the trip the optimizer sees once the user has picked a cabin."""

import copy
import re
from datetime import date, timedelta

from .charts import PRICERS, airports, chart_options
from .fares import SearchBudgetExceeded, get_fare
from .visa import fx

CABINS = ["economy", "premium_economy", "business", "first"]
RANK = {c: i for i, c in enumerate(CABINS)}
MAX_TRIPS = 8
MAX_DAYS_AHEAD = 330  # stay inside Google Flights' booking window


class FareUnavailable(Exception):
    pass


def effective_trip(base: dict, cabin: str) -> dict:
    """Cash option priced in `cabin`; award options kept only if in `cabin` or better.

    Each award is valued at the cash fare of the cabin it actually books, the standard
    cents-per-point basis. A lower-cabin award isn't offered for a higher-cabin request.
    """
    trip = copy.deepcopy(base)
    trip["cabin"] = cabin
    try:
        fare = get_fare(trip, cabin)
    except SearchBudgetExceeded as e:
        raise FareUnavailable(str(e)) from e
    if fare:
        trip["cash_price_usd"] = fare["price"]
    elif cabin != base["cabin"] or base.get("cash_price_usd") is None:
        raise FareUnavailable(f"No {cabin.replace('_', ' ')} fare found for {base['label']}")
    trip["fare"] = fare

    # Charted programs are priced from their official chart in the booked cabin; the rest are sample.
    options = [_with_fee({**o, "fare": fare, "cash_price_usd": trip["cash_price_usd"]}) for o in chart_options(trip, cabin)]
    for opt in base["award_options"]:
        if opt["program"] in PRICERS:
            continue
        if RANK[opt["cabin"]] < RANK[cabin]:
            continue
        opt_fare = fare if opt["cabin"] == cabin else get_fare(trip, opt["cabin"])
        opt = {**opt, "fare": opt_fare, "award_source": {"type": "sample"}}
        if opt_fare:
            opt["cash_price_usd"] = opt_fare["price"]
        elif opt["cabin"] == cabin:
            opt["cash_price_usd"] = trip["cash_price_usd"]
        elif "cash_price_usd" not in opt:
            continue  # no way to value this award
        options.append(opt)
    trip["award_options"] = options
    trip["local_fx"] = _local_fx(trip)
    return trip


def _with_fee(opt: dict) -> dict:
    """Convert a published foreign-currency fee to USD at Visa's rate; it reduces the award's value."""
    fee = opt.pop("fee", None)
    if not fee:
        return opt
    usd = fx.convert(fee["amount"], fee["currency"], "USD")
    opt["fees_usd"] = usd["amount"] if usd else 0
    opt["award_source"] = {**opt["award_source"], "fee": {**fee, "usd": usd}}
    return opt


def _local_fx(trip: dict) -> dict | None:
    """Visa's rate from USD into the destination's currency (shown on trips abroad)."""
    ap = airports().get(trip.get("destination", ""))
    currency = fx.COUNTRY_CURRENCY.get(ap[1]) if ap else None
    if not currency or currency == "USD":
        return None
    r = fx.rate("USD", currency)
    return {"currency": currency, **r} if r else None


def _city(code: str) -> str:
    ap = airports().get(code)
    name = (ap[5] if ap and len(ap) > 5 and ap[5] else code) if ap else code
    return re.sub(r"\s*\(.*\)", "", name).strip() or code


def custom_trip(origin: str, destination: str, outbound_date: str, cabin: str, label: str | None = None) -> dict:
    """A user-entered trip. Its id comes from route + date, so the same trip reuses its saved fare."""
    origin, destination = origin.strip().upper(), destination.strip().upper()
    ap = airports()
    for code in (origin, destination):
        if code not in ap:
            raise ValueError(f"Unknown airport code: {code}")
    if origin == destination:
        raise ValueError("Origin and destination must differ")
    if cabin not in CABINS:
        raise ValueError(f"Unknown cabin: {cabin}")
    try:
        day = date.fromisoformat(outbound_date)
    except ValueError as e:
        raise ValueError(f"Invalid date: {outbound_date}") from e
    today = date.today()
    if not today < day <= today + timedelta(days=MAX_DAYS_AHEAD):
        raise ValueError(f"Date must be between tomorrow and {MAX_DAYS_AHEAD} days from today")
    return {
        "id": f"c-{origin}-{destination}-{day.isoformat()}",
        "label": (label or "").strip() or _city(destination),
        "origin": origin,
        "destination": destination,
        "outbound_date": day.isoformat(),
        "month": day.isoformat()[:7],
        "cabin": cabin,
        "cash_price_usd": None,  # priced from a live fare
        "award_options": [],  # charted programs are priced automatically
        "custom": True,
    }
