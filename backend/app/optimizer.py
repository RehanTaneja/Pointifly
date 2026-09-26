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
  sum_{t,o} x[h,t,o] <= B_h                 no holding is overdrawn

  maximize  sum V_o * y[t,o]  -  sum reserve_h * x[h,t,o]

reserve_h is what a point in holding h is worth if you keep it, so an award only wins
if it beats holding the points. Cash is net zero: you pay the fare and get the fare.

Greedy runs the *same* model one trip at a time in date order, deducting balances
after each booking. The only difference between the two is scope.
"""

from dataclasses import dataclass, field
from fractions import Fraction
from math import lcm

from ortools.sat.python import cp_model

CASH = "cash"
SCALE = 100  # objective in 1/100 cent so fractional reserve values stay integral
# Lexicographic objective: value first, then fewest transfers pooled per award, then
# holding order. Each weight exceeds the largest possible total of the terms below it.
TIE = 1_000_000_000
SPLIT = 10_000_000


@dataclass
class Option:
    key: str  # "cash" or program id
    program: str | None
    points: int
    value_cents: int
    cabin: str


@dataclass
class TripPlan:
    trip: dict
    option: Option
    sources: dict[str, int] = field(default_factory=dict)  # holding -> points moved


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
            )
        )
    return opts


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
) -> Plan | None:
    """Optimal plan for `trips` together. force_points=trip id disallows cash for that trip."""
    m = cp_model.CpModel()
    holdings = list(balances)
    y: dict[tuple[str, int], cp_model.IntVar] = {}
    x: dict[tuple[str, str, int], cp_model.IntVar] = {}
    options = {t["id"]: trip_options(t) for t in trips}
    main_terms, tie_terms = [], []

    for t in trips:
        tid = t["id"]
        for i, o in enumerate(options[tid]):
            y[tid, i] = m.new_bool_var(f"y_{tid}_{i}")
            if o.key == CASH:
                continue  # cash is net zero: pay the fare, get the fare
            main_terms.append(o.value_cents * SCALE * y[tid, i])
            covered = []
            for rank, h in enumerate(holdings):
                ratio = _reach(h, o.program, transfers)
                if ratio is None or balances[h] == 0:
                    continue
                v = m.new_int_var(0, balances[h], f"x_{h}_{tid}_{i}")
                x[h, tid, i] = v
                used = m.new_bool_var(f"u_{h}_{tid}_{i}")
                m.add(v <= balances[h] * used)
                m.add_implication(used, y[tid, i])
                covered.append((ratio, v))
                main_terms.append(-round(reserve_cpp.get(h, 0) * SCALE) * v)
                # Tie-breaks: fewest sources per award, then points already in the program,
                # then holdings in list order.
                tie_terms.append(SPLIT * used)
                tie_terms.append((0 if h == o.program else rank + 1) * v)
            if not covered:
                m.add(y[tid, i] == 0)
                continue
            # sum_h ratio_h * x_h >= P * y, scaled by the common denominator
            den = lcm(*(r.denominator for r, _ in covered))
            m.add(sum(int(r * den) * v for r, v in covered) >= o.points * den * y[tid, i])
        m.add_exactly_one(y[tid, i] for i in range(len(options[tid])))
        if force_points == tid:
            m.add(y[tid, 0] == 0)

    for h in holdings:
        used = [v for (hh, _, _), v in x.items() if hh == h]
        if used:
            m.add(sum(used) <= balances[h])

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
        plans.append(TripPlan(t, options[tid][i], sources))
    return Plan(plans, after, int(solver.value(main)))


def greedy(
    trips: list[dict],
    balances: dict[str, int],
    transfers: dict[str, dict[str, float]],
    reserve_cpp: dict[str, float],
) -> Plan:
    """Same model, one trip at a time in date order: what trip-by-trip award tools do."""
    remaining = dict(balances)
    plans, objective = [], 0
    for t in sorted(trips, key=lambda t: t["month"]):
        step = solve([t], remaining, transfers, reserve_cpp)
        assert step is not None  # cash is always feasible
        plans.append(step.trips[0])
        remaining = step.balances_after
        objective += step.objective
    return Plan(plans, remaining, objective)

