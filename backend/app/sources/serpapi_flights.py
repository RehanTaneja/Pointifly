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


def lowest_fare(response: dict) -> dict | None:
    """Cheapest itinerary across best_flights and other_flights, or None if nothing priced."""
    itineraries = [i for i in response.get("best_flights", []) + response.get("other_flights", []) if i.get("price")]
    if not itineraries:
        return None
    best = min(itineraries, key=lambda i: i["price"])
    return {
        "price": best["price"],
        "airlines": sorted({f["airline"] for f in best.get("flights", []) if f.get("airline")}),
        "price_level": response.get("price_insights", {}).get("price_level"),
    }


def search(params: dict, api_key: str) -> dict:
    return get_json(URL, {**params, "api_key": api_key})
