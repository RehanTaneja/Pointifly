"""Runs greedy and portfolio optimizers and turns their plans into the API response,
including a plain-English reason for every decision."""

from . import card_rewards
from .data_store import holding_names, load_dataset
from .models import Allocation, Balance, OptimizeResponse, StrategyResult
from .optimizer import CASH, Plan, TripPlan, greedy, solve

OBJ_PER_USD = 100 * 100  # optimizer objective is in 1/100 cent


def _route(tp: TripPlan, names: dict[str, str]) -> str:
    srcs = [h for h in tp.sources if h != tp.option.program]
    direct = tp.option.program in tp.sources
    parts = []
    if srcs:
        parts.append(f"Transfer {' + '.join(names[h] for h in srcs)} → {names[tp.option.program]}")
    if direct:
        parts.append(f"use {names[tp.option.program]} miles" if srcs else f"Use {names[tp.option.program]} miles")
    return ", ".join(parts)


def _cpp(tp: TripPlan) -> float:
    """Cents of fare value per point, net of the award's cash fees."""
    return (tp.option.value_cents - tp.option.fees_cents) / tp.option.points


def _net_cents(tp: TripPlan) -> int:
    return 0 if tp.option.key == CASH else tp.option.value_cents - tp.option.fees_cents


def _award_option(tp: TripPlan) -> dict:
    """The dataset award option a plan chose (fare it's measured against, price source)."""
    for opt in tp.trip["award_options"]:
        if opt["program"] == tp.option.program and opt["cabin"] == tp.option.cabin:
            return opt
    return {}


def _describe_change(before: TripPlan, after: TripPlan, names: dict[str, str]) -> str:
    def label(tp: TripPlan) -> str:
        if tp.option.key == CASH:
            return "cash"
        return f"{names[tp.option.program]} {tp.option.cabin} ({_cpp(tp):.1f}¢/pt)"

    return f"{before.trip['label']} from {label(before)} to {label(after)}"


class Planner:
    def __init__(self, trips: list[dict], balances: dict[str, int], card_ids: list[str] | None = None):
        ds = load_dataset()
        self.trips = trips
        # Fixed holding order so tie-breaks don't depend on the order the client sent.
        self.names = holding_names()
        order = list(self.names)
        self.balances = dict(sorted(balances.items(), key=lambda kv: order.index(kv[0])))
        self.transfers = {c["id"]: c["transfers"] for c in ds["currencies"]}
        self.increments = {
            c["id"]: {pid: d["increment"] for pid, d in c["transfer_details"].items()} for c in ds["currencies"]
        }
        self.reserve_default = ds["reserve_value_cpp"]["default"]
        # Visa cards that can pay cash legs (default: the Visa cards that earn into the user's holdings).
        if card_ids is None:
            card_ids = [cid for cid, c in card_rewards.cards().items() if c["earns"] in balances]
        self.visa_ids = card_rewards.visa_card_ids(card_ids)
        self.earn = {t["id"]: card_rewards.earn_options(t, self.visa_ids) for t in trips}
        holdings = set(balances) | {h for opts in self.earn.values() for _, h, _ in opts}
        self.reserve = {h: ds["reserve_value_cpp"].get(h, self.reserve_default) for h in holdings}

    def _solve(self, trips: list[dict], balances: dict[str, int], force_points: str | None = None) -> Plan | None:
        earn = {t["id"]: self.earn.get(t["id"], []) for t in trips}
        return solve(trips, balances, self.transfers, self.reserve, force_points, self.increments, earn)

    def run(self) -> OptimizeResponse:
        g = greedy(self.trips, self.balances, self.transfers, self.reserve, self.increments, self.earn)
        p = self._solve(self.trips, self.balances)
        assert p is not None  # paying cash for everything is always feasible
        greedy_res = self._result("Greedy (trip-by-trip)", g, self._greedy_reason)
        portfolio_res = self._result("Pointifly (whole year)", p, lambda tp: self._portfolio_reason(tp, p))
        return OptimizeResponse(
            mock=False,
            greedy=greedy_res,
            portfolio=portfolio_res,
            points_saved=greedy_res.total_points - portfolio_res.total_points,
            value_gained_usd=portfolio_res.total_value_usd - greedy_res.total_value_usd,
            sankey=self._sankey(portfolio_res),
        )

    # --- reasons -------------------------------------------------------------

    def _points_reason(self, tp: TripPlan) -> str:
        article = "an" if tp.option.cabin[0] in "aeiou" else "a"
        return f"{_route(tp, self.names)}: {_cpp(tp):.1f}¢/pt on {article} {tp.option.cabin} fare."

    def _greedy_reason(self, tp: TripPlan) -> str:
        alone = self._solve([tp.trip], self.balances).trips[0]
        base = self._points_reason(tp) if tp.option.key != CASH else "No affordable award beats keeping the points."
        if alone.option.key != tp.option.key:
            return f"{base} Its best standalone option was no longer affordable after earlier bookings."
        return f"{base} Best option for this trip on its own."

    def _portfolio_reason(self, tp: TripPlan, plan: Plan) -> str:
        if tp.option.key != CASH:
            return self._points_reason(tp)
        tid = tp.trip["id"]
        forced = self._solve(self.trips, self.balances, force_points=tid)
        if forced is None:
            return "Not enough points reach any award for this trip."
        forced_tp = next(t for t in forced.trips if t.trip["id"] == tid)
        loss = (plan.objective - forced.objective) / OBJ_PER_USD
        knock_on = [
            _describe_change(before, after, self.names)
            for before, after in zip(plan.trips, forced.trips)
            if before.trip["id"] != tid and _net_cents(after) < _net_cents(before)  # only trips that lose out
        ]
        using = f"Using points here ({self.names[forced_tp.option.program]}, {_cpp(forced_tp):.1f}¢/pt)"
        if knock_on:
            return f"{using} would push {'; '.join(knock_on)}. Net cost: ${loss:,.0f}."
        if loss > 0:
            return f"{using} is below the {self.reserve_default:.1f}¢/pt reserve value. Keep the points."
        return f"{using} is worth the same as cash. Keeping the points."

    # --- response shaping ----------------------------------------------------

    def _result(self, name: str, plan: Plan, reason) -> StrategyResult:
        allocs = []
        for tp in plan.trips:
            is_cash = tp.option.key == CASH
            allocs.append(
                Allocation(
                    trip_id=tp.trip["id"],
                    trip_label=tp.trip["label"],
                    method="cash" if is_cash else "points",
                    program=tp.option.program,
                    cabin=tp.option.cabin,
                    sources=[Balance(holding=h, points=v) for h, v in tp.sources.items()],
                    points=sum(tp.sources.values()),
                    award_points=0 if is_cash else tp.option.points,
                    cash_usd=(tp.option.value_cents if is_cash else tp.option.fees_cents) / 100,
                    fees_usd=0 if is_cash else tp.option.fees_cents / 100,
                    value_usd=0 if is_cash else tp.option.value_cents / 100,
                    cents_per_point=None if is_cash else round(_cpp(tp), 2),
                    reason=reason(tp),
                    fare=tp.trip.get("fare") if is_cash else _award_option(tp).get("fare"),
                    award_source=None if is_cash else _award_option(tp).get("award_source"),
                    local_fx=tp.trip.get("local_fx"),
                    payment_card=self._payment_card(tp),
                )
            )
        return StrategyResult(
            name=name,
            allocations=allocs,
            total_points=sum(a.points for a in allocs),
            total_value_usd=sum(a.value_usd for a in allocs),
            cash_out_of_pocket_usd=sum(a.cash_usd for a in allocs),
            points_earned=sum(a.payment_card["earned_points"] for a in allocs if a.payment_card),
            remaining_balances=[Balance(holding=h, points=v) for h, v in plan.balances_after.items()],
        )

    def _payment_card(self, tp: TripPlan) -> dict | None:
        if not tp.card:
            return None
        cid, holding, pts = tp.card
        c = card_rewards.cards()[cid]
        return {
            "id": cid,
            "name": c["name"],
            "tier": c["tier"],
            "holding": holding,
            "rate": card_rewards.airfare_rate(cid, (tp.trip.get("fare") or {}).get("airlines")),
            "earned_points": pts,
            "source_url": c["source_url"],
        }

    def _sankey(self, result: StrategyResult) -> dict[str, list]:
        """holding -> program -> trip, plus holding -> 'Preserved' for unspent points. Units: points."""
        nodes: list[dict] = []
        index: dict[str, int] = {}

        def node(key: str, label: str) -> int:
            if key not in index:
                index[key] = len(nodes)
                nodes.append({"name": label})
            return index[key]

        links: dict[tuple[int, int], int] = {}

        def link(a: int, b: int, v: int) -> None:
            links[a, b] = links.get((a, b), 0) + v

        for a in result.allocations:
            if a.method != "points":
                continue
            trip = node(f"t:{a.trip_id}", a.trip_label)
            for s in a.sources:
                src = node(f"h:{s.holding}", self.names[s.holding])
                if s.holding == a.program:
                    link(src, trip, s.points)
                else:
                    prog = node(f"p:{a.program}", self.names[a.program])
                    link(src, prog, s.points)
                    link(prog, trip, s.points)
        for b in result.remaining_balances:
            if b.points > 0:
                link(node(f"h:{b.holding}", self.names[b.holding]), node("preserved", "Preserved"), b.points)
        return {"nodes": nodes, "links": [{"source": s, "target": t, "value": v} for (s, t), v in links.items()]}
