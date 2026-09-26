"""Parsers and snapshot overlay. Fixtures use only the documented response fields."""

from app.data_store import apply_snapshot, load_base_dataset
from app.sources import serpapi_flights

TRIP = {"id": "del", "origin": "ATL", "destination": "DEL", "outbound_date": "2027-03-12"}


def test_serpapi_params_one_way_and_round_trip():
    p = serpapi_flights.build_params(TRIP, "business")
    assert p["type"] == 2 and p["travel_class"] == 3 and "return_date" not in p
    rt = serpapi_flights.build_params({**TRIP, "return_date": "2027-03-20"}, "economy")
    assert rt["type"] == 1 and rt["travel_class"] == 1 and rt["return_date"] == "2027-03-20"


def _leg(airline, cabin):
    return {"airline": airline, "travel_class": cabin}


def test_serpapi_lowest_fare_across_best_and_other():
    resp = {
        "best_flights": [{"price": 900, "flights": [_leg("Delta", "Economy")]}],
        "other_flights": [
            {"price": 750, "flights": [_leg("Air India", "Economy"), _leg("United", "Economy")]},
            {"flights": []},
        ],
        "price_insights": {"price_level": "low"},
    }
    fare = serpapi_flights.lowest_fare(resp, "economy")
    assert (fare["price"], fare["airlines"], fare["price_level"]) == (750, ["Air India", "United"], "low")
    assert [f["airline"] for f in fare["itinerary"]["flights"]] == ["Air India", "United"]
    assert serpapi_flights.lowest_fare({}, "economy") is None


def test_serpapi_business_ignores_mixed_cabin_itineraries():
    # Real shape seen for ATL-NRT: cheapest "business" result had a premium economy leg.
    resp = {
        "other_flights": [
            {"price": 2695, "flights": [_leg("WestJet", "Premium Economy"), _leg("WestJet", "Business Class")]},
            {"price": 4913, "flights": [_leg("Air Canada", "Business Class"), _leg("Air Canada", "Business Class")]},
        ]
    }
    assert serpapi_flights.lowest_fare(resp, "business")["price"] == 4913
    assert serpapi_flights.lowest_fare(resp, "premium_economy") is None


def test_snapshot_overrides_fetched_values_only():
    base = load_base_dataset()
    snap = {
        "cash_fares": {
            "del:business": {"price": 3999, "source": "Google Flights via SerpApi", "fetched_at": "2026-09-25T00:00:00+00:00"},
            "del:economy": {"price": 812, "source": "Google Flights via SerpApi", "fetched_at": "2026-09-25T00:00:00+00:00"},
        },
    }
    ds = apply_snapshot(base, snap)
    trips = {t["id"]: t for t in ds["sample_trips"]}
    assert trips["del"]["cash_price_usd"] == 3999 and trips["del"]["cash_source"]["source"].startswith("Google")
    assert next(o for o in trips["del"]["award_options"] if o.get("cabin") == "economy")["cash_price_usd"] == 812
    assert trips["mia"]["cash_price_usd"] == next(t for t in base["sample_trips"] if t["id"] == "mia")["cash_price_usd"]
    assert base["sample_trips"][2]["cash_price_usd"] != 3999  # base untouched


def test_program_match_phrases_do_not_collide():
    names = {"Air Canada Aeroplan": "aeroplan", "ANA Mileage Club": "ana", "Turkish Airlines Miles&Smiles": "turkish"}
    programs = load_base_dataset()["programs"]
    for name, expected in names.items():
        hits = [p["id"] for p in programs if any(n in name.lower() for n in p["match"])]
        assert hits == [expected], (name, hits)


def test_recent_fares_are_not_refetched():
    from datetime import datetime, timedelta, timezone

    from app.sources.refresh import is_fresh  # noqa: E402

    params = {"departure_id": "ATL"}
    now = datetime.now(timezone.utc)
    assert is_fresh({"params": params, "fetched_at": now.isoformat()}, params)
    assert not is_fresh({"params": params, "fetched_at": (now - timedelta(days=4)).isoformat()}, params)
    assert not is_fresh({"params": {"departure_id": "JFK"}, "fetched_at": now.isoformat()}, params)  # search changed
    assert not is_fresh(None, params)


def test_transfer_ratios_file_is_complete_and_sourced():
    ds = load_base_dataset()
    programs = {p["id"] for p in ds["programs"]}
    for cur in ds["currencies"]:
        src = cur["transfer_source"]
        assert src["url"].startswith("https://") and src["verified_on"]
        assert cur["transfer_details"], cur["id"]
        for pid, d in cur["transfer_details"].items():
            assert pid in programs, (cur["id"], pid)
            assert d["ratio"] > 0 and d["increment"] >= 1 and d["minimum"] >= d["increment"]
            assert d["quoted"]  # the issuer's own wording
    # Spot-check against the issuers' pages as verified 2026-09-26.
    t = {c["id"]: c["transfers"] for c in ds["currencies"]}
    assert "united" not in t["amex_mr"] and "turkish" not in t["amex_mr"]
    assert "ana" not in t["chase_ur"] and "turkish" not in t["chase_ur"]
    assert "united" not in t["capital_one"] and "ana" not in t["capital_one"]
