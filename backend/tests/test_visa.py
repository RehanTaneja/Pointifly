from fastapi.testclient import TestClient

from app.main import app
from app.trips import effective_trip
from app.visa import client, fx, offers

api = TestClient(app)


def fx_calls(fake):
    return [c for c in fake.calls if c[1].startswith("/forexrates")]


def test_rate_is_cached_per_pair_per_day(fake_visa):
    assert fx.rate("USD", "JPY")["rate"] == 141.43
    assert fx.rate("USD", "JPY")["rate"] == 141.43
    assert len(fx_calls(fake_visa)) == 1  # second lookup served from the cache
    assert fx.rate("USD", "USD")["rate"] == 1.0 and len(fx_calls(fake_visa)) == 1


def test_convert_and_unknown_currency(fake_visa):
    assert fx.convert(39, "CAD", "USD")["amount"] == 28.08
    assert fx.rate("USD", "XXX") is None and fx_calls(fake_visa) == [("POST", "/forexrates/v2/foreignexchangerates")]


def test_falls_back_to_last_known_rate_when_visa_fails(fake_visa, monkeypatch):
    fx._write_cache({"USD->JPY": {"rate": 140.0, "date": "2026-09-01", "source": fx.SOURCE}})

    def down(*a, **k):
        raise client.VisaError(503, "unavailable")

    monkeypatch.setattr(client, "call", down)
    assert fx.rate("USD", "JPY") == {"rate": 140.0, "date": "2026-09-01", "source": fx.SOURCE}  # dated, stale
    assert fx.rate("USD", "GBP") is None  # nothing cached, nothing invented


def test_no_calls_when_not_configured(fake_visa, monkeypatch):
    monkeypatch.setattr(client, "configured", lambda: False)
    assert fx.rate("USD", "JPY") is None and fake_visa.calls == []


def test_aeroplan_fee_converted_and_deducted(fake_visa, monkeypatch):
    from app import trips as T

    monkeypatch.setattr(T, "get_fare", lambda trip, cabin: {"price": 4000})
    base = {"id": "d", "label": "Delhi", "origin": "ATL", "destination": "DEL", "cabin": "business",
            "cash_price_usd": 1, "award_options": []}
    t = effective_trip(base, "business")
    aero = next(o for o in t["award_options"] if o["program"] == "aeroplan")
    assert aero["fees_usd"] == 28.08  # $39 CAD at the (fake) Visa rate 0.72
    assert aero["award_source"]["fee"]["currency"] == "CAD" and aero["award_source"]["fee"]["usd"]["amount"] == 28.08
    ana = next(o for o in t["award_options"] if o["program"] == "ana")
    assert "fees_usd" not in ana  # no published fee in the ANA chart
    assert t["local_fx"]["currency"] == "INR" and t["local_fx"]["rate"] == 83.5


def test_domestic_trip_has_no_local_fx(fake_visa, monkeypatch):
    from app import trips as T

    monkeypatch.setattr(T, "get_fare", lambda trip, cabin: {"price": 150})
    base = {"id": "m", "label": "Miami", "origin": "ATL", "destination": "MIA", "cabin": "economy",
            "cash_price_usd": 1, "award_options": []}
    assert effective_trip(base, "economy")["local_fx"] is None


REAL = {"offerId": 1, "offerTitle": "$250 Airline Fee Credit", "offerShortDescription": {"text": "Pick your favorite airline"},
        "merchantList": [{"merchant": "VPP UBS"}], "categorySubcategoryList": [{"key": 129, "value": "Protection"}],
        "redemptionCountries": [{"value": "United States of America"}], "cardProductList": [{"value": "Visa Infinite"}],
        "redemptionUrl": '&lt;a href="https://www.visainfinitehotels.com" &gt;x&lt;/a&gt;',
        "imageList": [{"fileLocation": "https://www.visa.com/x.jpg"}], "validityToDate": "Nov 11, 2099 GMT"}


def test_offer_filter_keeps_real_travel_offers_only():
    placeholder = {**REAL, "offerId": 2, "offerTitle": "20140825_Test Offer"}
    lorem = {**REAL, "offerId": 3, "offerTitle": "45% off", "offerShortDescription": {"text": "Lorem ipsum travel"}}
    not_travel = {**REAL, "offerId": 4, "offerTitle": "Free shipping", "offerShortDescription": {"text": "Flowers"}}
    canada = {**REAL, "offerId": 5, "redemptionCountries": [{"value": "Canada"}]}
    out = offers.travel_offers([REAL, placeholder, lorem, not_travel, canada])
    assert [o["id"] for o in out] == [1]
    assert out[0]["url"] == "https://www.visainfinitehotels.com" and out[0]["cards"] == ["Visa Infinite"]


def test_benefits_endpoint_calls_vmorc_once_per_day(fake_visa):
    fake_visa.offers = [REAL]
    assert [o["title"] for o in api.get("/api/visa/benefits").json()["offers"]] == ["$250 Airline Fee Credit"]
    api.get("/api/visa/benefits")
    assert fake_visa.calls.count(("GET", "/vmorc/offers/v1/all")) == 1


def test_optimize_includes_fee_and_local_fx(fake_visa):
    r = api.post("/api/optimize", json={}).json()
    allocs = r["portfolio"]["allocations"] + r["greedy"]["allocations"]
    aero = [a for a in allocs if a["program"] == "aeroplan"]
    assert aero and all(a["fees_usd"] == 28.08 for a in aero)
    assert {a["local_fx"]["currency"] for a in allocs if a["local_fx"]} == {"GBP", "INR", "JPY"}
