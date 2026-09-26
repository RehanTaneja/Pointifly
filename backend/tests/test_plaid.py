"""Plaid integration. A fake Plaid (documented request/response shapes) runs the flow offline;
the live Sandbox test runs automatically when PLAID_CLIENT_ID / PLAID_SECRET are set."""

import json
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.plaid import client, routes
from app.plaid.cards import cards_from_accounts, classify

api = TestClient(app)


INSTITUTION_NAMES = {"ins_10": "American Express", "ins_56": "Chase", "ins_128026": "Capital One", "ins_109508": "First Platypus Bank"}


class FakePlaid:
    """Implements the four endpoints we call, per https://plaid.com/docs/api/."""

    def __init__(self):
        self.items: dict[str, dict] = {}  # access_token -> {institution_id, accounts}
        self.public: dict[str, dict] = {}
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, path: str, body: dict) -> dict:
        self.calls.append((path, body))
        if path == "/link/token/create":
            assert body["products"] and body["user"]["client_user_id"] and body["country_codes"] == ["US"]
            return {"link_token": "link-sandbox-123", "expiration": "2026-09-26T12:00:00Z"}
        if path == "/sandbox/public_token/create":
            cfg = json.loads(body["options"]["override_password"])
            accounts = [
                {"account_id": f"acc{i}", "name": a["meta"]["name"], "official_name": a["meta"].get("official_name"),
                 "mask": a["meta"]["mask"], "type": a["type"], "subtype": a["subtype"]}
                for i, a in enumerate(cfg["override_accounts"])
            ]
            token = f"public-sandbox-{len(self.public)}"
            self.public[token] = {"institution_id": body["institution_id"], "accounts": accounts}
            return {"public_token": token}
        if path == "/item/public_token/exchange":
            item = self.public.pop(body["public_token"])
            access = f"access-sandbox-{len(self.items)}"
            self.items[access] = item
            return {"access_token": access, "item_id": f"item-{len(self.items)}"}
        if path == "/accounts/get":
            item = self.items[body["access_token"]]
            ins = item["institution_id"]
            return {"accounts": item["accounts"], "item": {"institution_id": ins, "institution_name": INSTITUTION_NAMES[ins]}}
        raise AssertionError(path)


@pytest.fixture
def fake(monkeypatch):
    f = FakePlaid()
    monkeypatch.setattr(client, "post", f)
    monkeypatch.setattr(client, "configured", lambda: True)
    monkeypatch.setattr(client, "plaid_env", lambda: "sandbox")
    routes._CONNECTIONS.clear()
    return f


@pytest.mark.parametrize(
    "name,holding",
    [
        ("Chase Sapphire Preferred", "chase_ur"),
        ("Chase Sapphire Reserve", "chase_ur"),
        ("Ink Business Preferred Credit Card", "chase_ur"),
        ("Chase Freedom Unlimited", "chase_ur"),
        ("United Explorer Card", "united"),
        ("American Express Gold Card", "amex_mr"),
        ("The Platinum Card from American Express", "amex_mr"),
        ("Capital One Venture Rewards", "capital_one"),
        ("Capital One VentureOne Rewards", "capital_one"),
        ("Capital One Venture X Rewards", "capital_one"),
        ("Chase Aeroplan Card", "aeroplan"),
        ("Plaid Credit Card", None),
        ("Delta SkyMiles Gold American Express Card", None),  # co-brand: earns SkyMiles, not Amex points
        ("Hilton Honors American Express Surpass Card", None),
        ("Marriott Bonvoy Brilliant American Express Card", None),
    ],
)
def test_classify(name, holding):
    assert classify({"name": name})[0] == holding


def test_cobrand_carries_note():
    holding, note = classify({"name": "Delta SkyMiles Platinum Card"})
    assert holding is None and "Co-branded" in note


def test_freedom_carries_transfer_note():
    holding, note = classify({"official_name": "Chase Freedom Flex"})
    assert holding == "chase_ur" and "Sapphire" in note


def test_only_credit_accounts_become_cards():
    cards = cards_from_accounts(
        {"accounts": [{"type": "depository", "name": "Checking"}, {"type": "credit", "name": "Chase Sapphire Preferred", "mask": "1"}],
         "item": {"institution_name": "Chase"}}
    )
    assert [(c["product"], c["holding"], c["institution"]) for c in cards] == [("Chase Sapphire Preferred", "chase_ur", "Chase")]


def test_presentation_flag(monkeypatch):
    monkeypatch.setenv("PRESENTATION_MODE", "1")
    assert api.get("/api/plaid/status").json()["presentation"] is True
    monkeypatch.setenv("PRESENTATION_MODE", "0")
    assert api.get("/api/plaid/status").json()["presentation"] is False


def test_status_and_unconfigured(monkeypatch):
    monkeypatch.setattr(client, "configured", lambda: False)
    assert api.get("/api/plaid/status").json()["configured"] is False
    assert api.post("/api/plaid/link_token").status_code == 503
    assert api.post("/api/plaid/exchange", json={"public_token": "x"}).status_code == 503


def test_link_token_and_exchange_flow(fake):
    assert api.post("/api/plaid/link_token").json() == {"link_token": "link-sandbox-123"}
    # Simulate Link onSuccess: a public token for a user holding one card.
    pt = client.sandbox_public_token("ins_109508", "user_custom", json.dumps({"override_accounts": [
        {"type": "credit", "subtype": "credit card", "meta": {"name": "American Express Gold Card", "mask": "1005"}}]}))
    r = api.post("/api/plaid/exchange", json={"public_token": pt, "institution_name": "American Express"}).json()
    assert r["cards"] == [{"product_id": "amex_gold", "network": "amex", "tier": None, "account_id": "acc0", "institution": "American Express",
                           "product": "American Express Gold Card", "mask": "1005", "holding": "amex_mr", "note": None}]
    assert "access" not in json.dumps(r)  # access tokens stay server-side
    assert list(routes._CONNECTIONS) == [r["connection_id"]]


def test_sandbox_demo_connects_all_demo_issuers(fake):
    r = api.post("/api/plaid/sandbox_demo").json()
    # Institution names come from Plaid (the issuers' own institution records).
    assert {(c["institution"], c["product"], c["holding"]) for c in r["cards"]} == {
        ("American Express", "American Express Gold Card", "amex_mr"),
        ("Chase", "Chase Sapphire Preferred", "chase_ur"),
        ("Chase", "United Explorer Card", "united"),
        ("Capital One", "Capital One Venture Rewards", "capital_one"),
    }
    sent = [b for p, b in fake.calls if p == "/sandbox/public_token/create"]
    assert all(b["options"]["override_username"] == "user_custom" for b in sent)
    assert "access-sandbox" not in json.dumps(r)


def test_sandbox_demo_refused_outside_sandbox(fake, monkeypatch):
    monkeypatch.setattr(client, "plaid_env", lambda: "production")
    assert api.post("/api/plaid/sandbox_demo").status_code == 400


def test_plaid_errors_surface_as_502(fake, monkeypatch):
    def boom(path, body):
        raise client.PlaidError(400, {"error_code": "INVALID_API_KEYS", "error_message": "invalid client_id or secret"})

    monkeypatch.setattr(client, "post", boom)
    r = api.post("/api/plaid/link_token")
    assert r.status_code == 502 and "INVALID_API_KEYS" in r.json()["detail"]


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1" or not client.configured() or client.plaid_env() != "sandbox",
    reason="live test: set RUN_LIVE_TESTS=1 (and Plaid Sandbox keys) to run",
)
def test_live_sandbox_demo():
    routes._CONNECTIONS.clear()
    r = api.post("/api/plaid/sandbox_demo")
    assert r.status_code == 200, r.text
    cards = r.json()["cards"]
    assert {c["holding"] for c in cards} == {"amex_mr", "chase_ur", "capital_one", "united"}
    assert {c["institution"] for c in cards} == {"American Express", "Chase", "Capital One"}
