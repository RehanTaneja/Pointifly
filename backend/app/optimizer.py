"""Greedy vs. portfolio points optimizer (exact integer program, OR-Tools CP-SAT).

Model
-----
For every trip t, pick exactly one way to pay: cash, or one of its award options o
(program p_o, price P_o points, fare value V_o). Points reach program p from holding h
either directly (h == p) or through a transfer at ratio r_hp.

  y[t,o]   in {0,1}      trip t is paid with option o (cash is an option)
  x[h,t,o] >= 0 integer  points moved out of holding h to pay for option o

  sum_o y[t,o] = 1                          one way to pay per trip
  sum_h r_hp * x[h,t,o] >= P_o * y[t,o]     transferred points cover the award
  used_h(up to t) <= B_h + earned_h(posted by t)   no holding is overdrawn

  x[h,t,o] = k * increment_h                transfers move in fixed blocks (e.g. 1,000)

  maximize  sum (V_o - F_o) * y[t,o]  -  sum reserve_h * x[h,t,o]

F_o is the award's taxes and fees in cash.

Paying cash with a Visa card earns points: for a cash trip, at most one card k is chosen
(z[t,k]), earning E_tk = rate_k * fare points into the card's holding. Earned points are
valued at the reserve value and can fund later trips once posted (POST_DAYS after the
cash trip), which is why the balance rule is checked at every trip date.

reserve_h is what a point in holding h is worth if you keep it, so an award only wins
if it beats holding the points. Cash is net zero: you pay the fare and get the fare.

Greedy runs the *same* model one trip at a time in date order, deducting balances
after each booking. The only difference between the two is scope.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from fractions import Fraction
from math import lcm

from ortools.sat.python import cp_model

CASH = "cash"
SCALE = 100  # objective in 1/100 cent so fractional reserve values stay integral
# Lexicographic objective: value first, then fewest transfers pooled per award, then
# holding order. Each weight exceeds the largest possible total of the terms below it.
TIE = 10_000_000_000
SPLIT = 100_000_000
POST_DAYS = 30  # earned points count toward trips at least this many days after the cash trip


@dataclass
class Option:
    key: str  # "cash" or program id
    program: str | None
    points: int
    value_cents: int
    cabin: str
    fees_cents: int = 0


@dataclass
class TripPlan:
    trip: dict
    option: Option
    sources: dict[str, int] = field(default_factory=dict)  # holding -> points moved
    card: tuple[str, str, int] | None = None  # (card id, holding, points earned) for a cash trip


@dataclass
class Plan:
    trips: list[TripPlan]
    balances_after: dict[str, int]
    objective: int  # in 1/100 cent, excluding tie-breaks


def trip_options(trip: dict) -> list[Option]:
    opts = [Option(CASH, None, 0, trip["cash_price_usd"] * 100, trip["cabin"])]
    for a in trip["award_options"]:
        opts.append(
            Option(
                key=a["program"],
                program=a["program"],
                points=a["points"],
                value_cents=round(a.get("cash_price_usd", trip["cash_price_usd"]) * 100),
                cabin=a.get("cabin", trip["cabin"]),
                fees_cents=round(a.get("fees_usd", 0) * 100),
            )
        )
    return opts


def trip_day(trip: dict) -> date:
    return date.fromisoformat(trip.get("outbound_date") or f"{trip['month']}-01")


def _reach(holding: str, program: str, transfers: dict[str, dict[str, float]]) -> Fraction | None:
    if holding == program:
        return Fraction(1)
    ratio = transfers.get(holding, {}).get(program)
    return Fraction(ratio).limit_denominator(100) if ratio else None


def solve(
    trips: list[dict],
    balances: dict[str, int],
    transfers: dict[str, dict[str, float]],
    reserve_cpp: dict[str, float],
    force_points: str | None = None,
    increments: dict[str, dict[str, int]] | None = None,
    earn: dict[str, list[tuple[str, str, int]]] | None = None,
) -> Plan | None:
    """Optimal plan for `trips` together. force_points=trip id disallows cash for that trip.

    earn: trip id -> [(card id, holding, points earned if that card pays the cash fare)].
    """
    m = cp_model.CpModel()
    increments, earn = increments or {}, earn or {}
    balances = dict(balances)
    for opts in earn.values():
        for _, h, _ in opts:
            balances.setdefault(h, 0)
    holdings = list(balances)
    # Most a holding could ever hold: its balance plus every point it could earn.
    cap = {h: balances[h] + sum(p for opts in earn.values() for _, hh, p in opts if hh == h) for h in holdings}
    y: dict[tuple[str, int], cp_model.IntVar] = {}
    x: dict[tuple[str, str, int], cp_model.LinearExpr] = {}
    z: dict[tuple[str, int], cp_model.IntVar] = {}
    options = {t["id"]: trip_options(t) for t in trips}
    main_terms, tie_terms = [], []

    for t_idx, t in enumerate(trips):
        tid = t["id"]
        for i, o in enumerate(options[tid]):
            y[tid, i] = m.new_bool_var(f"y_{tid}_{i}")
            if o.key == CASH:
                # Cash is net zero (pay the fare, get the fare), plus what the paying card earns.
                for k, (_, h, pts) in enumerate(earn.get(tid, [])):
                    z[tid, k] = m.new_bool_var(f"z_{tid}_{k}")
                    m.add_implication(z[tid, k], y[tid, i])
                    main_terms.append(round(reserve_cpp.get(h, 0) * SCALE) * pts * z[tid, k])
                    tie_terms.append(k * z[tid, k])  # equal value: prefer the card listed first
                if earn.get(tid):
                    m.add(sum(z[tid, k] for k in range(len(earn[tid]))) <= 1)
                continue
            main_terms.append((o.value_cents - o.fees_cents) * SCALE * y[tid, i])
            covered = []
            for rank, h in enumerate(holdings):
                ratio = _reach(h, o.program, transfers)
                if ratio is None or cap[h] == 0:
                    continue
                # Transfers move in fixed blocks; miles already in the program move freely.
                inc = 1 if h == o.program else increments.get(h, {}).get(o.program, 1)
                blocks = m.new_int_var(0, cap[h] // inc, f"k_{h}_{tid}_{i}")
                v = inc * blocks
                x[h, tid, i] = v
                used = m.new_bool_var(f"u_{h}_{tid}_{i}")
                m.add(v <= cap[h] * used)
                m.add_implication(used, y[tid, i])
                covered.append((ratio, v))
                main_terms.append(-round(reserve_cpp.get(h, 0) * SCALE) * v)
                # Tie-breaks: fewest sources per award, then points already in the program,
                # then earlier holdings go to earlier trips.
                tie_terms.append(SPLIT * used)
                tie_terms.append((0 if h == o.program else (rank + 1) * (len(trips) - t_idx)) * v)
            if not covered:
                m.add(y[tid, i] == 0)
                continue
            # sum_h ratio_h * x_h >= P * y, scaled by the common denominator
            den = lcm(*(r.denominator for r, _ in covered))
            m.add(sum(int(r * den) * v for r, v in covered) >= o.points * den * y[tid, i])
        m.add_exactly_one(y[tid, i] for i in range(len(options[tid])))
        if force_points == tid:
            m.add(y[tid, 0] == 0)

    # Balance rule at every trip date: points used so far <= balance + earnings already posted.
    days = {t["id"]: trip_day(t) for t in trips}
    for h in holdings:
        for d in sorted(set(days.values())):
            used = [v for (hh, tid, _), v in x.items() if hh == h and days[tid] <= d]
            if not used:
                continue
            posted = [
                pts * z[tid, k]
                for tid, opts in earn.items()
                if tid in days and days[tid] + timedelta(days=POST_DAYS) <= d
                for k, (_, hh, pts) in enumerate(opts)
                if hh == h
            ]
            m.add(sum(used) <= balances[h] + sum(posted))

    main = sum(main_terms)
    m.maximize(main * TIE - sum(tie_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10
    status = solver.solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    plans, after = [], dict(balances)
    for t in trips:
        tid = t["id"]
        i = next(i for i in range(len(options[tid])) if solver.value(y[tid, i]))
        sources = {h: solver.value(v) for (h, tt, ii), v in x.items() if tt == tid and ii == i and solver.value(v)}
        for h, pts in sources.items():
            after[h] -= pts
        card = next((earn[tid][k] for k in range(len(earn.get(tid, []))) if solver.value(z[tid, k])), None)
        if card:
            after[card[1]] += card[2]
        plans.append(TripPlan(t, options[tid][i], sources, card))
    return Plan(plans, after, int(solver.value(main)))


def greedy(
    trips: list[dict],
    balances: dict[str, int],
    transfers: dict[str, dict[str, float]],
    reserve_cpp: dict[str, float],
    increments: dict[str, dict[str, int]] | None = None,
    earn: dict[str, list[tuple[str, str, int]]] | None = None,
) -> Plan:
    """Same model, one trip at a time in date order: what trip-by-trip award tools do.
    Points earned paying cash post POST_DAYS later, as in the whole-year model."""
    earn = earn or {}
    remaining = dict(balances)
    pending: list[tuple[date, str, int]] = []  # (posts on, holding, points)
    plans, objective = [], 0
    for t in sorted(trips, key=trip_day):
        for item in [p for p in pending if p[0] <= trip_day(t)]:
            remaining[item[1]] = remaining.get(item[1], 0) + item[2]
            pending.remove(item)
        step = solve([t], remaining, transfers, reserve_cpp, increments=increments, earn={t["id"]: earn.get(t["id"], [])})
        assert step is not None  # cash is always feasible
        tp = step.trips[0]
        plans.append(tp)
        remaining = step.balances_after
        if tp.card:  # earned points aren't spendable until they post
            remaining[tp.card[1]] -= tp.card[2]
            pending.append((trip_day(t) + timedelta(days=POST_DAYS), tp.card[1], tp.card[2]))
        objective += step.objective
    for _, h, pts in pending:
        remaining[h] = remaining.get(h, 0) + pts
    return Plan(plans, remaining, objective)

