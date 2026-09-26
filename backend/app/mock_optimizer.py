"""Hardcoded optimizer output over the sample dataset.

This is a stand-in so the UI can be built end to end. It will be replaced by the
real greedy + portfolio solvers (OR-Tools/PuLP). Allocations are hand-picked to
reproduce the demo narrative from the build doc:
  - Pay cash for Miami, transfer Amex -> Aeroplan for Delhi, preserve Chase for Tokyo.
  - Greedy spends 80,000 more points and gets $3,200 less travel value.
"""

from .data_store import holding_names, load_dataset
from .models import Allocation, Balance, OptimizeResponse, StrategyResult


def _trip(trip_id: str) -> dict:
    return next(t for t in load_dataset()["sample_trips"] if t["id"] == trip_id)


def _points_alloc(trip_id: str, source: str, program: str, points: int, value: float, reason: str) -> Allocation:
    return Allocation(
        trip_id=trip_id,
        trip_label=_trip(trip_id)["label"],
        method="points",
        source=source,
        program=program,
        points=points,
        value_usd=value,
        cents_per_point=round(value / points * 100, 2),
        reason=reason,
    )


def _cash_alloc(trip_id: str, reason: str) -> Allocation:
    t = _trip(trip_id)
    return Allocation(
        trip_id=trip_id, trip_label=t["label"], method="cash", cash_usd=t["cash_price_usd"], reason=reason
    )


GREEDY = [
    _points_alloc("mia", "amex_mr", "british_airways", 18000, 180,
                  "Best points option for Miami on its own."),
    _points_alloc("lhr", "chase_ur", "virgin_atlantic", 100000, 3000,
                  "Best points option for London on its own."),
    _points_alloc("del", "united", "united", 90000, 2650,
                  "Amex left with 82k after Miami: can't reach the 90k Aeroplan award."),
    _points_alloc("nrt", "capital_one", "aeroplan", 80000, 1500,
                  "Chase drained by London: Tokyo falls back to an economy award."),
]

PORTFOLIO = [
    _cash_alloc("mia", "Using points here blocks a 5x-better redemption on Delhi (1.0¢ vs 5.0¢/pt)."),
    _points_alloc("lhr", "capital_one", "flying_blue", 30000, 750,
                  "Capital One covers London so Amex and Chase stay free for premium trips."),
    _points_alloc("del", "amex_mr", "aeroplan", 90000, 4500,
                  "Transfer Amex -> Aeroplan for business class at 5.0¢/pt."),
    _points_alloc("nrt", "chase_ur", "virgin_atlantic", 88000, 5280,
                  "Chase preserved for Tokyo: Chase -> Virgin Atlantic business class."),
]


def _strategy(name: str, allocs: list[Allocation], balances: list[Balance]) -> StrategyResult:
    remaining = {b.holding: b.points for b in balances}
    for a in allocs:
        if a.source:
            remaining[a.source] -= a.points
    return StrategyResult(
        name=name,
        allocations=allocs,
        total_points=sum(a.points for a in allocs),
        total_value_usd=sum(a.value_usd for a in allocs),
        cash_out_of_pocket_usd=sum(a.cash_usd for a in allocs),
        remaining_balances=[Balance(holding=h, points=p) for h, p in remaining.items()],
    )


def _sankey(result: StrategyResult) -> dict[str, list]:
    """holding -> program -> trip, plus holding -> 'Preserved' for unspent points. Units: points."""
    names = holding_names()
    nodes: list[dict] = []
    index: dict[str, int] = {}

    def node(key: str, label: str) -> int:
        if key not in index:
            index[key] = len(nodes)
            nodes.append({"name": label})
        return index[key]

    links: list[dict] = []
    for a in result.allocations:
        if a.method != "points":
            continue
        src = node(f"h:{a.source}", names[a.source])
        prog = node(f"p:{a.program}", names[a.program])
        trip = node(f"t:{a.trip_id}", a.trip_label)
        if a.source != a.program:  # transfer step
            links.append({"source": src, "target": prog, "value": a.points})
            links.append({"source": prog, "target": trip, "value": a.points})
        else:
            links.append({"source": src, "target": trip, "value": a.points})
    for b in result.remaining_balances:
        if b.points > 0:
            links.append({"source": node(f"h:{b.holding}", names[b.holding]),
                          "target": node("preserved", "Preserved"), "value": b.points})
    return {"nodes": nodes, "links": links}


def optimize_mock() -> OptimizeResponse:
    balances = [Balance(**b) for b in load_dataset()["sample_balances"]]
    greedy = _strategy("Greedy (trip-by-trip)", GREEDY, balances)
    portfolio = _strategy("Pointfolio (whole year)", PORTFOLIO, balances)
    return OptimizeResponse(
        mock=True,
        greedy=greedy,
        portfolio=portfolio,
        points_saved=greedy.total_points - portfolio.total_points,
        value_gained_usd=portfolio.total_value_usd - greedy.total_value_usd,
        sankey=_sankey(portfolio),
    )
