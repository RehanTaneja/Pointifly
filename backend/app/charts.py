"""Award prices from official published charts (Aeroplan, ANA): one-way, points only.

A chart price says what an award costs *if* award space exists; it doesn't check seats,
and taxes/fees are not included. Programs without a chart keep sample prices.
"""

import json
import math
from functools import lru_cache

from .data_store import DATA_DIR

AEROPLAN_ZONE_NAMES = {"NA": "North America", "ATL": "Atlantic", "PAC": "Pacific", "SA": "South America"}
EARTH_RADIUS_MI = 3958.8


@lru_cache
def airports() -> dict[str, list]:
    return json.loads((DATA_DIR / "airports.json").read_text())["airports"]


@lru_cache
def charts() -> dict:
    return json.loads((DATA_DIR / "award_charts.json").read_text())


def distance_miles(a: str, b: str) -> float | None:
    """Great-circle distance in statute miles between two IATA airports."""
    ap = airports()
    if a not in ap or b not in ap:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (ap[a][3], ap[a][4], ap[b][3], ap[b][4]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def _band_label(bands: list[dict], i: int) -> str:
    lo = 0 if i == 0 else bands[i - 1]["max_miles"] + 1
    hi = bands[i]["max_miles"]
    return f"{lo:,}+ mi" if hi is None else f"{lo:,}–{hi:,} mi"


def aeroplan_price(origin: str, dest: str, cabin: str) -> dict | None:
    c = charts()["aeroplan"]
    ap = airports()
    if origin not in ap or dest not in ap:
        return None
    if {ap[origin][2], ap[dest][2]} & set(c["excluded_regions"]):
        return None
    za, zb = c["country_zone"].get(ap[origin][1]), c["country_zone"].get(ap[dest][1])
    if not za or not zb:
        return None
    bands = c["bands"].get("|".join(sorted([za, zb])))
    miles = distance_miles(origin, dest)
    if not bands or miles is None:
        return None
    for i, band in enumerate(bands):
        if band["max_miles"] is None or round(miles) <= band["max_miles"]:
            points = band.get(cabin)
            if not points:
                return None
            zones = " ↔ ".join(dict.fromkeys([AEROPLAN_ZONE_NAMES[za], AEROPLAN_ZONE_NAMES[zb]]))
            return {
                "points": points,
                "detail": (
                    f"{zones} · {round(miles):,} mi great-circle · {_band_label(bands, i)} band · partner airlines"
                    " (priced on distance flown, so connections can land in a higher band)"
                ),
            }
    return None


def ana_price(origin: str, dest: str, cabin: str) -> dict | None:
    c = charts()["ana"]
    ap = airports()
    if origin not in ap or dest not in ap:
        return None

    def zone(code: str) -> str | None:
        _, country, region, *_ = ap[code]
        return c["region_zone"].get(region) or c["country_zone"].get(country)

    za, zb = zone(origin), zone(dest)
    row = c["table"].get(f"{za}|{zb}") if za and zb else None
    points = row.get(cabin) if row else None
    if not points:
        return None
    return {"points": points, "detail": f"Zone {za} → Zone {zb} · partner airlines"}


PRICERS = {"aeroplan": aeroplan_price, "ana": ana_price}


def chart_options(trip: dict, cabin: str) -> list[dict]:
    """One award option per charted program that prices this route and cabin."""
    out = []
    for program, pricer in PRICERS.items():
        price = pricer(trip.get("origin", ""), trip.get("destination", ""), cabin)
        if not price:
            continue
        c = charts()[program]
        out.append(
            {
                "program": program,
                "points": price["points"],
                "cabin": cabin,
                "fee": c.get("partner_booking_fee"),  # published per-ticket fee, in its own currency
                "award_source": {
                    "type": "chart",
                    "title": c["source_title"],
                    "url": c["source_url"],
                    "effective": c["effective"],
                    "detail": price["detail"],
                    "notes": "Published price: award seat availability not checked; taxes/fees not included.",
                },
            }
        )
    return out
