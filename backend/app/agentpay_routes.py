"""Payment endpoints. Inputs are strict: unknown fields are rejected, ids and trip names are
limited to safe characters, amounts are bounded. There is no SQL database anywhere in
Pointifly, and nothing from a request is ever used to build a query or a shell command."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from . import agentpay

router = APIRouter(prefix="/api")

PlanId = Field(pattern=r"^[A-Za-z0-9_-]{8,40}$")
TripRef = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9 .\-]+$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MandateRequest(Strict):
    plan_id: str = PlanId
    autopay: bool
    max_per_payment: float = Field(gt=0, le=20000)
    max_total: float = Field(gt=0, le=50000)


class PayRequest(Strict):
    plan_id: str = PlanId
    trip: str = TripRef


def _call(fn, *args):
    try:
        return fn(*args)
    except KeyError as e:
        raise HTTPException(404, str(e.args[0])) from e


@router.post("/agent/mandate")
def set_mandate(req: MandateRequest) -> dict:
    return _call(agentpay.set_mandate, req.plan_id, req.autopay, req.max_per_payment, req.max_total)


@router.get("/agent/status")
def agent_status(plan_id: str = Query(pattern=r"^[A-Za-z0-9_-]{8,40}$")) -> dict:
    return _call(agentpay.status, plan_id)


@router.post("/agent/pay")
def agent_pay(req: PayRequest) -> dict:
    """The agent's only payment path: autopay toggle and spending limits always apply."""
    return _call(agentpay.pay, req.plan_id, req.trip, "agent")


@router.post("/pay")
def user_pay(req: PayRequest) -> dict:
    """The user's own Pay tap: amount and card still come from the server's plan."""
    return _call(agentpay.pay, req.plan_id, req.trip, "user")
