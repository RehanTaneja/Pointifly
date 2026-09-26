import itertools

from app.data_store import load_dataset
from app.optimizer import CASH, greedy, solve

DS = load_dataset()
TRANSFERS = {c["id"]: c["transfers"] for c in DS["currencies"]}
TRIPS = DS["sample_trips"]
HOLDINGS = ["amex_mr", "chase_ur", "capital_one", "united"]


def reserve(balances):
    return {h: 1.0 for h in balances}


def trip(tid, month, cash, options, cabin="economy"):
    return {"id": tid, "label": tid, "month": month, "cabin": cabin, "cash_price_usd": cash, "award_options": options}


def test_scarce_points_go_to_the_higher_value_trip():
    # 100k points, two trips that each cost 100k. Greedy books the earlier, worse one.
    trips = [
        trip("cheap", "2027-01", 1500, [{"program": "aeroplan", "points": 100000}]),
        trip("premium", "2027-02", 5000, [{"program": "aeroplan", "points": 100000}]),
    ]
    bal = {"amex_mr": 100000}
    g = greedy(trips, bal, TRANSFERS, reserve(bal))
    p = solve(trips, bal, TRANSFERS, reserve(bal))
    assert [t.option.key for t in g.trips] == ["aeroplan", CASH]
    assert [t.option.key for t in p.trips] == [CASH, "aeroplan"]


def test_award_below_reserve_value_pays_cash():
    trips = [trip("t", "2027-01", 100, [{"program": "aeroplan", "points": 20000}])]  # 0.5¢/pt
    bal = {"amex_mr": 50000}
    assert solve(trips, bal, TRANSFERS, reserve(bal)).trips[0].option.key == CASH


def test_pools_currencies_into_one_program():
    trips = [trip("t", "2027-01", 5000, [{"program": "aeroplan", "points": 90000}])]
    bal = {"amex_mr": 50000, "capital_one": 50000}
    plan = solve(trips, bal, TRANSFERS, reserve(bal))
    assert plan.trips[0].option.key == "aeroplan"
    assert sum(plan.trips[0].sources.values()) == 90000


def test_invariants_across_balance_mixes():
    for a, c, k in itertools.product(range(0, 160001, 80000), repeat=3):
        if a + c + k > 400000:
            continue
        bal = dict(zip(HOLDINGS, [a, c, k, 400000 - a - c - k]))
        g = greedy(TRIPS, bal, TRANSFERS, reserve(bal))
        p = solve(TRIPS, bal, TRANSFERS, reserve(bal))
        # Whole-year optimum can never do worse than trip-by-trip.
        assert p.objective >= g.objective
        for plan in (g, p):
            assert all(v >= 0 for v in plan.balances_after.values())  # never overdrawn
            for tp in plan.trips:
                if tp.option.key != CASH:
                    assert sum(tp.sources.values()) >= tp.option.points  # award fully paid (1:1 ratios)
