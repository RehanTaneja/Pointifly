"""Builds the trip the optimizer sees once the user has picked a cabin."""

import copy

from .charts import PRICERS, airports, chart_options
from .fares import get_fare
from .visa import fx

CABINS = ["economy", "premium_economy", "business", "first"]
RANK = {c: i for i, c in enumerate(CABINS)}


class FareUnavailable(Exception):
    pass


def effective_trip(base: dict, cabin: str) -> dict:
    """Cash option priced in `cabin`; award options kept only if in `cabin` or better.

    Each award is valued at the cash fare of the cabin it actually books, the standard
    cents-per-point basis. A lower-cabin award isn't offered for a higher-cabin request.
    """
    trip = copy.deepcopy(base)
    trip["cabin"] = cabin
    fare = get_fare(trip, cabin)
    if fare:
        trip["cash_price_usd"] = fare["price"]
    elif cabin != base["cabin"]:
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
