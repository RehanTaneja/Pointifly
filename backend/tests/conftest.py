"""Every test runs against fake Visa and Google Flights (SerpApi) APIs with temporary caches and
snapshot copies, so the suite never spends real API calls or edits committed data files."""

import os
import shutil
import urllib.request

import pytest

LIVE = os.environ.get("RUN_LIVE_TESTS") == "1"


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch):
    """Safety net: no test reaches a real API (and spends quota) unless RUN_LIVE_TESTS=1."""
    if LIVE:
        return

    def blocked(req, *a, **k):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        raise RuntimeError(f"real network call blocked in tests: {url.split('?')[0]}")

    monkeypatch.setattr(urllib.request, "urlopen", blocked)

from app import data_store, fares
from app.sources import serpapi_flights
from app.visa import client, fx, offers

FAKE_RATES = {("124", "840"): "0.7200", ("840", "392"): "141.4300", ("840", "356"): "83.5000", ("840", "826"): "0.7500"}


class FakeVisa:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.offers: list[dict] = []

    def __call__(self, method, path, body=None, timeout=20):
        self.calls.append((method, path))
        if path == "/forexrates/v2/foreignexchangerates":
            rate = FAKE_RATES[(body["sourceCurrencyCode"], body["destinationCurrencyCode"])]
            return {"conversionRate": rate, "destinationAmount": "0", "rateProductCode": "A"}
        if path == "/vmorc/offers/v1/all":
            return {"Offers": self.offers, "ReturnedResults": len(self.offers)}
        raise AssertionError(f"unexpected Visa call {method} {path}")


@pytest.fixture(autouse=True)
def fake_visa(monkeypatch, tmp_path):
    fake = FakeVisa()
    monkeypatch.setattr(client, "call", fake)
    monkeypatch.setattr(client, "configured", lambda: True)
    monkeypatch.setattr(fx, "CACHE_PATH", tmp_path / "visa_fx_rates.json")
    monkeypatch.setattr(offers, "CACHE_PATH", tmp_path / "visa_offers.json")
    return fake


class FakeSerpApi:
    """Returns canned Google Flights responses; any search without one fails the test."""

    def __init__(self):
        self.responses: dict[tuple[str, str, str, int], dict] = {}
        self.calls: list[dict] = []

    def add(self, origin, destination, date, travel_class, price, airline="Test Air", cls="Economy"):
        self.responses[(origin, destination, date, travel_class)] = {
            "best_flights": [{"price": price, "flights": [{"airline": airline, "travel_class": cls,
                              "departure_airport": {"id": origin}, "arrival_airport": {"id": destination}}]}],
            "search_metadata": {"google_flights_url": "https://www.google.com/travel/flights?test"},
        }

    def __call__(self, params, api_key):
        self.calls.append(params)
        key = (params["departure_id"], params["arrival_id"], params["outbound_date"], params["travel_class"])
        if key not in self.responses:
            raise AssertionError(f"real SerpApi search blocked in tests: {key}")
        return self.responses[key]


@pytest.fixture(autouse=True)
def fake_serpapi(monkeypatch, tmp_path):
    fake = FakeSerpApi()
    monkeypatch.setattr(serpapi_flights, "search", fake)
    snap = tmp_path / "snapshots.json"
    shutil.copy(data_store.SNAPSHOT_PATH, snap)  # committed fares stay readable, writes go to tmp
    monkeypatch.setattr(data_store, "SNAPSHOT_PATH", snap)
    monkeypatch.setattr(fares, "SNAPSHOT_PATH", snap)
    monkeypatch.setattr(fares, "RAW_DIR", tmp_path / "raw")
    data_store.load_dataset.cache_clear()
    yield fake
    data_store.load_dataset.cache_clear()


class FakeCybersource:
    """Mimics Cybersource's create-payment responses (documented fields); records requests."""

    def __init__(self):
        self.requests: list[dict] = []
        self.response = (201, {"id": "7400000000000000000000", "status": "AUTHORIZED", "reconciliationId": "R123",
                               "processorInformation": {"approvalCode": "831000"}})

    def __call__(self, config, body):
        assert config["run_environment"] == "apitest.cybersource.com"
        self.requests.append(body)
        return self.response


@pytest.fixture(autouse=True)
def fake_cybersource(monkeypatch):
    from app.cybersource import checkout

    fake = FakeCybersource()
    monkeypatch.setattr(checkout, "_send", fake)
    monkeypatch.setattr(checkout, "_PAID", {})
    for k, v in {"CYBERSOURCE_MERCHANT_ID": "test_merchant", "CYBERSOURCE_KEY_ID": "kid", "CYBERSOURCE_SECRET_KEY": "c2VjcmV0"}.items():
        monkeypatch.setenv(k, v)
    return fake


class FakeGemini:
    def __init__(self):
        self.calls: list[str] = []
        self.output: dict = {"balances": [], "trips": [], "unclear": []}

    def __call__(self, text, response_schema):
        self.calls.append(text)
        return self.output


class FakeElevenLabs:
    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.startswith("/v1/convai/conversation/get-signed-url"):
            return {"signed_url": "wss://api.elevenlabs.io/v1/convai/conversation?agent_id=a&conversation_signature=s"}
        if path == "/v1/convai/knowledge-base/text":
            return {"id": f"doc{len(self.calls)}", "name": body["name"]}
        if path.endswith("/rag-index"):
            return {"status": "succeeded"}
        if path == "/v1/convai/tools":
            return {"id": f"tool_{body['tool_config']['name']}"}
        if path == "/v1/convai/agents/create":
            return {"agent_id": "agent_test"}
        if method == "PATCH" and path.startswith("/v1/convai/agents/"):
            return {"agent_id": path.rsplit("/", 1)[1]}
        raise AssertionError(f"unexpected ElevenLabs call {method} {path}")


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch, tmp_path):
    from app.ai import parser, voice

    gemini, eleven = FakeGemini(), FakeElevenLabs()
    monkeypatch.setattr(parser, "_call", gemini)
    monkeypatch.setattr(parser, "_CACHE", {})
    monkeypatch.setattr(voice, "_request", eleven)
    monkeypatch.setattr(voice, "SETUP_STATE", tmp_path / "elevenlabs_setup.json")
    for k, v in {"GEMINI_API_KEY": "test-gemini", "ELEVENLABS_API_KEY": "test-eleven", "ELEVENLABS_AGENT_ID": "agent_test"}.items():
        monkeypatch.setenv(k, v)
    return gemini, eleven
