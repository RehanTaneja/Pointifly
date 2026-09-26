"""Builds the trip the optimizer sees once the user has picked a cabin."""

import copy

from .fares import get_fare

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

    options = []
    for opt in base["award_options"]:
        if RANK[opt["cabin"]] < RANK[cabin]:
            continue
        opt_fare = fare if opt["cabin"] == cabin else get_fare(trip, opt["cabin"])
        opt = {**opt, "fare": opt_fare}
        if opt_fare:
            opt["cash_price_usd"] = opt_fare["price"]
        elif opt["cabin"] == cabin:
            opt["cash_price_usd"] = trip["cash_price_usd"]
        elif "cash_price_usd" not in opt:
            continue  # no way to value this award
        options.append(opt)
    trip["award_options"] = options
    return trip
