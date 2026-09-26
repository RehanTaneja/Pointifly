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


def test_optimize_sample_portfolio_beats_greedy():
    r = client.post("/api/optimize", json={}).json()
    assert r["mock"] is False
    assert r["value_gained_usd"] > 0  # the claim that matters; points spent can go either way
    cash = [a for a in r["portfolio"]["allocations"] if a["method"] == "cash"]
    assert cash and all(a["reason"] for a in cash)


def test_optimize_without_body():
    assert client.post("/api/optimize").status_code == 200


def test_optimize_rejects_unknown_input():
    assert client.post("/api/optimize", json={"balances": [{"holding": "nope", "points": 1}]}).status_code == 400
    assert client.post("/api/optimize", json={"trip_ids": ["nope"]}).status_code == 400


def test_sankey_links_are_valid():
    s = client.post("/api/optimize", json={}).json()["sankey"]
    n = len(s["nodes"])
    assert all(0 <= l["source"] < n and 0 <= l["target"] < n and l["value"] > 0 for l in s["links"])


def test_optimize_independent_of_balance_order_and_no_fragment_splits():
    ds = client.get("/api/dataset").json()
    bal = ds["sample_balances"]
    a = client.post("/api/optimize", json={"balances": bal}).json()
    b = client.post("/api/optimize", json={"balances": bal[::-1]}).json()
    assert a["portfolio"] == b["portfolio"] and a["greedy"] == b["greedy"]
    for alloc in a["portfolio"]["allocations"]:
        assert len(alloc["sources"]) <= 2


def test_cabin_override_filters_lower_cabin_awards_and_attaches_fares():
    r = client.post("/api/optimize", json={"cabins": {"del": "business"}}).json()
    for strategy in ("greedy", "portfolio"):
        for a in r[strategy]["allocations"]:
            if a["trip_id"] == "del" and a["method"] == "points":
                assert a["cabin"] == "business"  # no economy award offered for a business request
    assert all("fare" in a for a in r["portfolio"]["allocations"])


def test_invalid_cabin_rejected():
    assert client.post("/api/optimize", json={"cabins": {"del": "lie-flat"}}).status_code == 400
    assert client.post("/api/optimize", json={"cabins": {"nope": "economy"}}).status_code == 400
