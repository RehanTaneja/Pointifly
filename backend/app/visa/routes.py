from fastapi import APIRouter

from . import client, fx, offers

router = APIRouter(prefix="/api/visa")


@router.get("/status")
def status() -> dict:
    return {"configured": client.configured()}


@router.get("/benefits")
def benefits() -> dict:
    return offers.get_travel_offers()


@router.get("/fx")
def fx_rate(src: str, dst: str) -> dict:
    return {"src": src, "dst": dst, "rate": fx.rate(src.upper(), dst.upper())}
