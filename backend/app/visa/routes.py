from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import card_rewards
from ..cybersource import checkout
from . import client, fx, offers

router = APIRouter(prefix="/api/visa")


class CheckoutRequest(BaseModel):
    trip_id: str
    amount_usd: float
    card_id: str


@router.get("/status")
def status() -> dict:
    return {"configured": client.configured(), "checkout_configured": checkout.configured()}


@router.post("/checkout")
def pay(req: CheckoutRequest) -> dict:
    """Pay a cash leg with a Visa card through the Cybersource Sandbox (test card, no money moves)."""
    if req.card_id not in card_rewards.visa_card_ids([req.card_id]):
        raise HTTPException(400, "Checkout needs a Visa card")
    try:
        result = checkout.pay(req.trip_id, req.amount_usd)
    except checkout.CheckoutError as e:
        raise HTTPException(503 if "not configured" in str(e) else 400, str(e)) from e
    return {**result, "card": card_rewards.cards()[req.card_id]["name"]}


@router.get("/benefits")
def benefits() -> dict:
    return offers.get_travel_offers()


@router.get("/fx")
def fx_rate(src: str, dst: str) -> dict:
    return {"src": src, "dst": dst, "rate": fx.rate(src.upper(), dst.upper())}
