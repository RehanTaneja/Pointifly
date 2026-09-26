"""Card products, networks and airfare earn rates (app/data/card_rewards.json, official issuer pages).

Pointifly pays cash legs with the user's Visa cards; each card earns its own points on airfare.
"""

import json
import math
import re
from functools import lru_cache

from .data_store import DATA_DIR


@lru_cache
def cards() -> dict[str, dict]:
    return json.loads((DATA_DIR / "card_rewards.json").read_text())["cards"]


def product_id(name: str) -> str | None:
    """Card product id for a card name from Plaid (or None if we don't know the product)."""
    text = (name or "").lower()
    for cid, c in cards().items():
        if re.search(c["match"], text):
            return cid
    return None


def visa_card_ids(ids: list[str]) -> list[str]:
    return [i for i in ids if cards().get(i, {}).get("network") == "visa"]


def airfare_rate(card_id: str, airlines: list[str] | None) -> float:
    """Points per $1 on this airfare; airline-specific rates apply when every flight is on that airline."""
    rates = cards()[card_id]["airfare"] or {}
    for airline, rate in rates.items():
        if airline != "default" and airlines and set(airlines) == {airline}:
            return rate
    return rates.get("default", 0)


def earn_options(trip: dict, visa_ids: list[str]) -> list[tuple[str, str, int]]:
    """[(card id, holding, points earned)] for paying this trip's cash fare with each Visa card."""
    fare = trip.get("fare") or {}
    out = []
    for cid in visa_ids:
        rate = airfare_rate(cid, fare.get("airlines"))
        pts = math.floor(rate * trip["cash_price_usd"])
        if pts > 0:
            out.append((cid, cards()[cid]["earns"], pts))
    return sorted(out, key=lambda o: -o[2])
