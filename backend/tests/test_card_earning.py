"""Paying cash legs with Visa cards: earn rates, card choice, and when earned points can be spent."""

from app import card_rewards
from app.data_store import load_dataset
from app.optimizer import CASH, greedy, solve

DS = load_dataset()
TRANSFERS = {c["id"]: c["transfers"] for c in DS["currencies"]}


def trip(tid, day, cash, options=(), airlines=None):
    return {"id": tid, "label": tid, "outbound_date": day, "month": day[:7], "cabin": "economy",
            "cash_price_usd": cash, "award_options": list(options), "fare": {"airlines": airlines or ["Delta"]}}


def test_product_matching_and_networks():
    assert card_rewards.product_id("Chase Sapphire Preferred") == "chase_sapphire_preferred"
    assert card_rewards.product_id("Capital One Venture Rewards") == "capital_one_venture"
    assert card_rewards.product_id("Capital One Venture X Rewards") is None  # different product, no verified rates
    assert card_rewards.product_id("United Explorer Card") == "united_explorer"
    assert card_rewards.visa_card_ids(["amex_gold", "chase_sapphire_preferred"]) == ["chase_sapphire_preferred"]


def test_airline_specific_rate():
    assert card_rewards.airfare_rate("united_explorer", ["United"]) == 3
    assert card_rewards.airfare_rate("united_explorer", ["United", "Air Canada"]) == 1
    assert card_rewards.airfare_rate("chase_sapphire_preferred", ["Delta"]) == 2


def test_earn_options_sorted_and_amex_excluded():
    t = trip("t", "2027-01-10", 500)
    opts = card_rewards.earn_options(t, card_rewards.visa_card_ids(["amex_gold", "united_explorer", "capital_one_venture"]))
    assert opts == [("capital_one_venture", "capital_one", 1000), ("united_explorer", "united", 500)]


def test_cash_trip_picks_the_best_earning_visa_card():
    t = trip("t", "2027-01-10", 500)
    earn = {"t": card_rewards.earn_options(t, ["united_explorer", "chase_sapphire_preferred"])}
    p = solve([t], {"chase_ur": 0}, TRANSFERS, {"chase_ur": 1.0, "united": 1.0}, earn=earn)
    assert p.trips[0].option.key == CASH and p.trips[0].card == ("chase_sapphire_preferred", "chase_ur", 1000)
    assert p.balances_after["chase_ur"] == 1000


def test_earned_points_fund_a_later_trip_only_after_posting():
    # Paying $5,000 cash in January earns 10,000 Chase points; the March award needs them.
    cash = trip("jan", "2027-01-10", 5000)
    award = [{"program": "united", "points": 10000, "cabin": "economy"}]
    later = trip("mar", "2027-03-10", 400, award)
    soon = trip("jan2", "2027-01-20", 400, award)  # only 10 days later: not posted yet
    earn = {"jan": [("chase_sapphire_preferred", "chase_ur", 10000)]}
    res = {"chase_ur": 1.0}
    p = solve([cash, later], {"chase_ur": 0}, TRANSFERS, res, earn=earn)
    assert [t.option.key for t in p.trips] == [CASH, "united"] and p.trips[1].sources == {"chase_ur": 10000}
    q = solve([cash, soon], {"chase_ur": 0}, TRANSFERS, res, earn=earn)
    assert [t.option.key for t in q.trips] == [CASH, CASH]


def test_greedy_applies_the_same_posting_rule():
    cash = trip("jan", "2027-01-10", 5000)
    later = trip("mar", "2027-03-10", 400, [{"program": "united", "points": 10000, "cabin": "economy"}])
    earn = {"jan": [("chase_sapphire_preferred", "chase_ur", 10000)]}
    g = greedy([cash, later], {"chase_ur": 0}, TRANSFERS, {"chase_ur": 1.0}, earn=earn)
    assert [t.option.key for t in g.trips] == [CASH, "united"]
    assert g.balances_after["chase_ur"] == 0


def test_no_visa_cards_means_no_earning():
    t = trip("t", "2027-01-10", 500)
    p = solve([t], {"chase_ur": 0}, TRANSFERS, {"chase_ur": 1.0}, earn={"t": []})
    assert p.trips[0].card is None
