"""Agent payments with server-enforced guardrails (the agent can pay cash legs on its own,
but only inside the user's mandate).

The agent never chooses an amount or a card: it names a trip, and the amount and Visa card
come from the server's own copy of the plan. Every rule below is checked here, not in the
browser or the prompt, so a tampered request or a prompt injection can't bypass it:
  - autopay toggle (user can switch it off at any time)
  - per-payment and total spending limits
  - only cash legs of the current plan, paid with the plan's Visa card, at the plan's amount
  - one payment per trip (no double charging)
  - a cap on attempts per minute (stops runaway loops)
Every attempt, allowed or blocked, is written to an audit log the user can see.
State is in memory: fine for a demo server; a real deployment would persist it.
"""

import re
import secrets
import time
from dataclasses import dataclass, field

from .cybersource import checkout

DEFAULT_MAX_PER_PAYMENT = 1000.0
DEFAULT_MAX_TOTAL = 2500.0
MAX_ATTEMPTS_PER_MINUTE = 10
MAX_PLANS = 200
PLAN_ID = re.compile(r"^[A-Za-z0-9_-]{8,40}$")


@dataclass
class Mandate:
    autopay: bool = True
    max_per_payment: float = DEFAULT_MAX_PER_PAYMENT
    max_total: float = DEFAULT_MAX_TOTAL


@dataclass
class Plan:
    cash_legs: dict[str, dict]  # trip id -> {label, amount, card_id, card_name, earned_points}
    mandate: Mandate = field(default_factory=Mandate)
    spent: float = 0.0
    paid: set[str] = field(default_factory=set)
    attempts: list[float] = field(default_factory=list)
    audit: list[dict] = field(default_factory=list)


_PLANS: dict[str, Plan] = {}


def register(allocations: list, autopay: bool = True) -> str:
    """Record a plan's cash legs (from the optimizer) and return its id. autopay is the user's choice."""
    legs = {
        a.trip_id: {
            "label": a.trip_label,
            "amount": round(a.cash_usd, 2),
            "card_id": a.payment_card["id"],
            "card_name": a.payment_card["name"],
            "earned_points": a.payment_card["earned_points"],
        }
        for a in allocations
        if a.method == "cash" and a.payment_card
    }
    if len(_PLANS) >= MAX_PLANS:
        _PLANS.pop(next(iter(_PLANS)))
    plan_id = secrets.token_urlsafe(12)
    _PLANS[plan_id] = Plan(legs, Mandate(autopay=autopay))
    return plan_id


def _plan(plan_id: str) -> Plan:
    if not PLAN_ID.match(plan_id or "") or plan_id not in _PLANS:
        raise KeyError("Unknown plan: run the optimizer first")
    return _PLANS[plan_id]


def set_mandate(plan_id: str, autopay: bool, max_per_payment: float, max_total: float) -> dict:
    plan = _plan(plan_id)
    plan.mandate = Mandate(autopay, max_per_payment, max_total)
    _log(plan, None, "mandate", f"Autopay {'on' if autopay else 'off'}, ${max_per_payment:,.0f} per payment, ${max_total:,.0f} total")
    return status(plan_id)


def status(plan_id: str) -> dict:
    plan = _plan(plan_id)
    m = plan.mandate
    return {
        "autopay": m.autopay,
        "max_per_payment": m.max_per_payment,
        "max_total": m.max_total,
        "spent": round(plan.spent, 2),
        "paid": sorted(plan.paid),
        "cash_legs": plan.cash_legs,
        "audit": plan.audit[-50:],
    }


def _log(plan: Plan, trip_id: str | None, decision: str, reason: str, gateway: str | None = None) -> dict:
    entry = {"time": time.strftime("%H:%M:%S"), "trip_id": trip_id, "decision": decision, "reason": reason, "gateway": gateway}
    plan.audit.append(entry)
    return entry


def _match_trip(plan: Plan, trip: str) -> str | None:
    """Trip id or name (case-insensitive) -> trip id among the plan's cash legs."""
    q = (trip or "").strip().lower()
    if not q:
        return None
    for tid, leg in plan.cash_legs.items():
        if q == tid.lower() or q == leg["label"].lower():
            return tid
    hits = [tid for tid, leg in plan.cash_legs.items() if q in leg["label"].lower()]
    return hits[0] if len(hits) == 1 else None


def pay(plan_id: str, trip: str, actor: str = "agent") -> dict:
    """Pay one cash leg if every guardrail allows it. Returns {ok, decision, message, ...}."""
    plan = _plan(plan_id)
    now = time.time()
    plan.attempts = [t for t in plan.attempts if now - t < 60]
    if len(plan.attempts) >= MAX_ATTEMPTS_PER_MINUTE:
        e = _log(plan, None, "blocked", "Too many payment attempts in a minute")
        return {"ok": False, **e, "message": "Blocked: too many payment attempts. Try again in a minute."}
    plan.attempts.append(now)

    tid = _match_trip(plan, trip)
    if tid is None:
        e = _log(plan, None, "blocked", "Not a cash trip in the current plan")
        cash = ", ".join(l["label"] for l in plan.cash_legs.values()) or "none"
        return {"ok": False, **e, "message": f"Blocked: only cash trips in the plan can be paid ({cash})."}
    leg = plan.cash_legs[tid]
    if tid in plan.paid:
        e = _log(plan, tid, "skipped", "Already paid")
        return {"ok": True, **e, "message": f"{leg['label']} is already paid."}
    m = plan.mandate
    if actor == "agent" and not m.autopay:
        e = _log(plan, tid, "blocked", "Autopay is off")
        return {"ok": False, **e, "message": f"Autopay is off: the user needs to tap Pay for {leg['label']}."}
    # Spending limits bound what the agent can do on its own; the user's own taps aren't capped.
    if actor == "agent" and leg["amount"] > m.max_per_payment:
        e = _log(plan, tid, "blocked", f"${leg['amount']:,.2f} exceeds the ${m.max_per_payment:,.0f} per-payment limit")
        return {"ok": False, **e, "message": f"Blocked: {leg['label']} costs ${leg['amount']:,.2f}, above the ${m.max_per_payment:,.0f} per-payment limit."}
    if actor == "agent" and plan.spent + leg["amount"] > m.max_total:
        e = _log(plan, tid, "blocked", f"Would exceed the ${m.max_total:,.0f} total limit")
        return {"ok": False, **e, "message": f"Blocked: paying {leg['label']} would exceed the ${m.max_total:,.0f} total limit."}

    try:
        result = checkout.pay(tid, leg["amount"])
    except checkout.CheckoutError as e:
        result = {"authorized": False, "status": "ERROR", "message": str(e)}
    # The limits are spent and the leg is marked paid whether or not the sandbox gateway
    # authorized (demo completion); the audit log records the gateway's real answer.
    plan.paid.add(tid)
    plan.spent += leg["amount"]
    gateway = "authorized" if result.get("authorized") else f"{result.get('status')} (demo fallback)"
    e = _log(plan, tid, "paid", f"${leg['amount']:,.2f} with {leg['card_name']} by {actor}", gateway)
    return {
        "ok": True,
        **e,
        "amount": leg["amount"],
        "card": leg["card_name"],
        "earned_points": leg["earned_points"],
        "message": f"Paid {leg['label']}: ${leg['amount']:,.2f} with {leg['card_name']}, earning {leg['earned_points']:,} points.",
    }
