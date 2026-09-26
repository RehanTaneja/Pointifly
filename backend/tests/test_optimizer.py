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


# --- edge cases ---------------------------------------------------------------

INC = {"amex_mr": 1000, "chase_ur": 1000, "capital_one": 1000}
DELHI = [trip("del", "2027-08", 4500, [{"program": "aeroplan", "points": 90000}], cabin="business")]


def plan_for(bal, trips=DELHI):
    return solve(trips, bal, TRANSFERS, reserve(bal), increments=INC)


def test_small_balance_alone_pays_cash_and_is_preserved():
    p = plan_for({"amex_mr": 2000})
    assert p.trips[0].option.key == CASH
    assert p.balances_after == {"amex_mr": 2000}


def test_small_balance_tops_up_another_currency():
    p = plan_for({"amex_mr": 2000, "chase_ur": 88000})
    assert p.trips[0].option.key == "aeroplan"
    assert p.trips[0].sources == {"amex_mr": 2000, "chase_ur": 88000}


def test_transfer_increments_are_respected():
    # 500 Amex can't move (below one 1,000 block) and Chase can only move 89,000 of 89,500.
    assert plan_for({"amex_mr": 500, "chase_ur": 89500}).trips[0].option.key == CASH
    # 1,500 Amex moves as 1,000; 1,000 + 89,000 reaches 90,000.
    p = plan_for({"amex_mr": 1500, "chase_ur": 89500})
    assert p.trips[0].option.key == "aeroplan"
    assert all(v % 1000 == 0 for v in p.trips[0].sources.values())


def test_program_miles_move_in_any_amount():
    p = solve(
        [trip("m", "2027-03", 180, [{"program": "united", "points": 12345}])],
        {"united": 12345}, TRANSFERS, {"united": 1.0}, increments=INC,
    )
    assert p.trips[0].sources == {"united": 12345}


def test_award_fees_can_make_cash_better():
    # $600 fare, 30k points: 2.0¢/pt before fees, (600-350)/30k = 0.83¢/pt after -> below 1.0¢ reserve.
    trips = [trip("t", "2027-01", 600, [{"program": "flying_blue", "points": 30000, "fees_usd": 350}])]
    assert plan_for({"amex_mr": 50000}, trips).trips[0].option.key == CASH


def test_no_balances_or_no_trips():
    assert all(t.option.key == CASH for t in plan_for({}).trips)
    assert plan_for({"amex_mr": 50000}, []).trips == []


def test_trip_without_award_options_pays_cash():
    assert plan_for({"amex_mr": 100000}, [trip("x", "2027-01", 300, [])]).trips[0].option.key == CASH
