"""Every test runs against a fake Visa API (documented response shapes) with temporary caches,
so the suite never spends real Visa calls or edits the committed cache files."""

import pytest

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
