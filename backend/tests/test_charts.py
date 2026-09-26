"""Chart lookups pinned to the official charts (Aeroplan 2026-08 PDF, ANA one-way partner chart)."""

from app.charts import aeroplan_price, ana_price, chart_options, charts, distance_miles
from app.trips import effective_trip


def pts(price):
    return price["points"] if price else None


def test_great_circle_distance_is_sane():
    assert 3420 < distance_miles("JFK", "LHR") < 3470
    assert distance_miles("JFK", "ZZZ") is None


def test_aeroplan_bands_and_zones():
    # North America <-> Atlantic, 6,001-8,000 mi, all other partners: 60,000 / 90,000 / 150,000
    assert [pts(aeroplan_price("ATL", "DEL", c)) for c in ("economy", "business", "first")] == [60000, 90000, 150000]
    # North America <-> Pacific, 5,001-7,500 mi: 50,000 / 85,000 / 120,000
    assert pts(aeroplan_price("ATL", "NRT", "business")) == 85000
    # Within North America, 501-1,500 mi: 10,000 economy; no first class row
    assert pts(aeroplan_price("ATL", "MIA", "economy")) == 10000
    assert aeroplan_price("ATL", "MIA", "first") is None
    # Partner rows have no premium economy price
    assert aeroplan_price("ATL", "LHR", "premium_economy") is None


def test_aeroplan_skips_unmapped_areas():
    assert aeroplan_price("ATL", "HNL", "economy") is None  # Hawaii excluded (zone unclear on the map)
    assert aeroplan_price("ATL", "KTM", "economy") is None  # Nepal: border area, no zone assigned


def test_ana_zones():
    assert pts(ana_price("ATL", "DEL", "business")) == 68000  # Zone 6 -> Zone 4
    assert pts(ana_price("ATL", "NRT", "business")) == 58500  # Japan one-way uses Zone 1-B
    assert pts(ana_price("NRT", "ATL", "business")) == 58500
    assert pts(ana_price("ATL", "HNL", "business")) == 42500  # Hawaii is its own zone (5)
    assert pts(ana_price("ATL", "MIA", "economy")) == 15000  # within North America
    assert ana_price("ATL", "LHR", "premium_economy") is None


def test_ana_table_is_symmetric():
    table = charts()["ana"]["table"]
    for key, row in table.items():
        a, b = key.split("|")
        assert table[f"{b}|{a}"] == row, key


def test_chart_options_carry_their_source():
    opts = {o["program"]: o for o in chart_options({"origin": "ATL", "destination": "DEL"}, "business")}
    assert set(opts) == {"aeroplan", "ana"}
    src = opts["aeroplan"]["award_source"]
    assert src["type"] == "chart" and src["url"].startswith("https://www.aircanada.com/") and src["effective"] == "2026-08"


def test_effective_trip_prices_charted_programs_from_the_chart(monkeypatch):
    from app import trips as T

    monkeypatch.setattr(T, "get_fare", lambda trip, cabin: {"price": 4000})
    base = {"id": "d", "label": "Delhi", "origin": "ATL", "destination": "DEL", "cabin": "business",
            "cash_price_usd": 1, "award_options": [{"program": "aeroplan", "points": 1, "cabin": "business"}]}
    t = effective_trip(base, "business")
    aero = [o for o in t["award_options"] if o["program"] == "aeroplan"]
    assert len(aero) == 1 and aero[0]["points"] == 90000 and aero[0]["award_source"]["type"] == "chart"
