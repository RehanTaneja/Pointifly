"""Live cash fares from Google Flights via SerpApi (free plan: 100 searches/month).

Docs: https://serpapi.com/google-flights-api
"""

from .http import get_json

URL = "https://serpapi.com/search"
TRAVEL_CLASS = {"economy": 1, "premium_economy": 2, "business": 3, "first": 4}


def build_params(trip: dict, cabin: str, currency: str = "USD") -> dict:
    """Search params for one trip. Round trip when the trip has a return_date, else one way."""
    params = {
        "engine": "google_flights",
        "departure_id": trip["origin"],
        "arrival_id": trip["destination"],
        "outbound_date": trip["outbound_date"],
        "travel_class": TRAVEL_CLASS[cabin],
        "currency": currency,
        "type": 1 if trip.get("return_date") else 2,
    }
    if trip.get("return_date"):
        params["return_date"] = trip["return_date"]
    return params


# Segment travel_class labels as returned by Google Flights (e.g. "Business Class").
CABIN_WORD = {"economy": "economy", "premium_economy": "premium", "business": "business", "first": "first"}


def _segment_cabin(label: str | None) -> str:
    return (label or "").lower().split(" ")[0]


def lowest_fare(response: dict, cabin: str) -> dict | None:
    """Cheapest itinerary whose every segment is in `cabin`, or None if nothing qualifies.

    Google Flights' "business" results include mixed-cabin trips (e.g. a premium economy
    connection); those would understate what a full business award is worth.
    """
    want = CABIN_WORD[cabin]
    itineraries = [
        i
        for i in response.get("best_flights", []) + response.get("other_flights", [])
        if i.get("price") and i.get("flights") and all(_segment_cabin(f.get("travel_class")) == want for f in i["flights"])
    ]
    if not itineraries:
        return None
    best = min(itineraries, key=lambda i: i["price"])
    return {
        "price": best["price"],
        "airlines": sorted({f["airline"] for f in best.get("flights", []) if f.get("airline")}),
        "price_level": response.get("price_insights", {}).get("price_level"),
        "itinerary": _itinerary(best),
        # Opens this exact search (route, date, cabin) on Google Flights.
        "google_flights_url": response.get("search_metadata", {}).get("google_flights_url"),
    }


def _itinerary(it: dict) -> dict:
    return {
        "total_duration_min": it.get("total_duration"),
        "flights": [
            {
                "airline": f.get("airline"),
                "flight_number": f.get("flight_number"),
                "from": f.get("departure_airport", {}).get("id"),
                "to": f.get("arrival_airport", {}).get("id"),
                "departs": f.get("departure_airport", {}).get("time"),
                "arrives": f.get("arrival_airport", {}).get("time"),
                "duration_min": f.get("duration"),
                "travel_class": f.get("travel_class"),
                "airplane": f.get("airplane"),
            }
            for f in it.get("flights", [])
        ],
        "layovers": [{"airport": l.get("id"), "duration_min": l.get("duration")} for l in it.get("layovers", [])],
    }


def search(params: dict, api_key: str) -> dict:
    return get_json(URL, {**params, "api_key": api_key})
