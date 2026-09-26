from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_dataset_shape_matches_doc():
    ds = client.get("/api/dataset").json()
    assert len(ds["currencies"]) == 3  # 3 transferable currencies
    assert 6 <= len(ds["programs"]) <= 8  # 6-8 programs
    assert 3 <= len(ds["sample_trips"]) <= 5  # 3-5 sample trips


def test_optimize_hits_demo_numbers():
    r = client.post("/api/optimize", json={}).json()
    assert r["mock"] is True
    assert r["points_saved"] == 80_000
    assert r["value_gained_usd"] == 3_200
    by_trip = {a["trip_id"]: a for a in r["portfolio"]["allocations"]}
    assert by_trip["mia"]["method"] == "cash"
    assert (by_trip["del"]["source"], by_trip["del"]["program"]) == ("amex_mr", "aeroplan")
    assert by_trip["nrt"]["source"] == "chase_ur"


def test_optimize_without_body():
    assert client.post("/api/optimize").status_code == 200


def test_sankey_links_are_valid():
    s = client.post("/api/optimize", json={}).json()["sankey"]
    n = len(s["nodes"])
    assert all(0 <= l["source"] < n and 0 <= l["target"] < n and l["value"] > 0 for l in s["links"])
