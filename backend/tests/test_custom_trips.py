from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import fares
from app.main import app
from app.trips import custom_trip

api = TestClient(app)
DAY = (date.today() + timedelta(days=60)).isoformat()
BAL = [{"holding": "amex_mr", "points": 80000}, {"holding": "chase_ur", "points": 60000}]


def body(*trips, **extra):
    return {"balances": BAL, "custom_trips": list(trips), **extra}


def paris(cabin="business", **k):
    return {"origin": "ATL", "destination": "CDG", "date": DAY, "cabin": cabin, **k}


def test_custom_trip_shape_and_stable_id():
    t = custom_trip("atl", "cdg", DAY, "business")
    assert t["id"] == f"c-ATL-CDG-{DAY}" and t["label"] == "Paris" and t["month"] == DAY[:7]
    assert custom_trip("ATL", "CDG", DAY, "business", label="Honeymoon")["label"] == "Honeymoon"


@pytest.mark.parametrize(
    "args,msg",
    [
        (("ATL", "ZZZ", DAY, "economy"), "Unknown airport"),
        (("ATL", "ATL", DAY, "economy"), "must differ"),
        (("ATL", "CDG", "2020-01-01", "economy"), "between tomorrow"),
        (("ATL", "CDG", (date.today() + timedelta(days=400)).isoformat(), "economy"), "between tomorrow"),
        (("ATL", "CDG", "next week", "economy"), "Invalid date"),
        (("ATL", "CDG", DAY, "lie-flat"), "Unknown cabin"),
    ],
)
def test_validation_runs_before_any_search(args, msg, fake_serpapi):
    with pytest.raises(ValueError, match=msg):
        custom_trip(*args)
    r = api.post("/api/optimize", json=body({"origin": args[0], "destination": args[1], "date": args[2], "cabin": args[3]}))
    assert r.status_code == 400 and fake_serpapi.calls == []


def test_custom_trip_priced_live_once_then_reused(fake_serpapi):
    fake_serpapi.add("ATL", "CDG", DAY, 3, 3100, airline="Air France", cls="Business Class")
    r1 = api.post("/api/optimize", json=body(paris())).json()
    r2 = api.post("/api/optimize", json=body(paris())).json()
    assert len(fake_serpapi.calls) == 1  # saved fare reused on the second run
    alloc = r1["portfolio"]["allocations"][0]
    r1.pop("plan_id"), r2.pop("plan_id")  # each run registers its own plan for payments
    assert alloc["trip_label"] == "Paris" and r1 == r2
    # Charts price the new route automatically: Aeroplan and ANA business ATL-CDG.
    if alloc["method"] == "points":
        assert alloc["program"] in {"aeroplan", "ana"} and alloc["award_source"]["type"] == "chart"


def test_custom_and_sample_trips_together(fake_serpapi):
    fake_serpapi.add("ATL", "CDG", DAY, 1, 640)
    r = api.post("/api/optimize", json=body(paris("economy"), trip_ids=["nrt"])).json()
    assert {a["trip_id"] for a in r["portfolio"]["allocations"]} == {"nrt", f"c-ATL-CDG-{DAY}"}
    assert len(fake_serpapi.calls) == 1  # the sample trip uses its saved fare


def test_no_fare_found_is_a_clear_error(fake_serpapi):
    fake_serpapi.responses[("ATL", "CDG", DAY, 4)] = {"best_flights": [], "other_flights": []}
    r = api.post("/api/optimize", json=body(paris("first")))
    assert r.status_code == 422 and "No first fare found for Paris" in r.json()["detail"]


def test_daily_search_cap(fake_serpapi, monkeypatch):
    monkeypatch.setenv("SERPAPI_DAILY_LIMIT", "1")
    fake_serpapi.add("ATL", "CDG", DAY, 1, 640)
    fake_serpapi.add("ATL", "LHR", DAY, 1, 520)
    assert api.post("/api/optimize", json=body(paris("economy"))).status_code == 200
    r = api.post("/api/optimize", json=body({"origin": "ATL", "destination": "LHR", "date": DAY, "cabin": "economy"}))
    assert r.status_code == 422 and "Daily live-search limit" in r.json()["detail"]
    assert len(fake_serpapi.calls) == 1 and fares.searches_today() == 1
    # Saved fares still work after the cap is hit.
    assert api.post("/api/optimize", json=body(paris("economy"))).status_code == 200


def test_trip_limit_and_duplicates(fake_serpapi):
    many = [{"origin": "ATL", "destination": d, "date": DAY, "cabin": "economy"}
            for d in ["CDG", "LHR", "FRA", "AMS", "MAD", "FCO", "ZRH", "MUC", "DUB"]]
    r = api.post("/api/optimize", json=body(*many))
    assert r.status_code == 400 and "At most 8" in r.json()["detail"]
    r = api.post("/api/optimize", json=body(paris(), paris()))
    assert r.status_code == 400 and "twice" in r.json()["detail"]
    assert fake_serpapi.calls == []


def test_airport_search():
    codes = [a["code"] for a in api.get("/api/airports?q=paris").json()]
    assert "CDG" in codes and "ORY" in codes
    assert api.get("/api/airports?q=cdg").json()[0]["code"] == "CDG"
    assert api.get("/api/airports?q=p").json() == []
