"""Plaid endpoints. Access tokens never leave the server; the browser gets a connection id."""

import secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import client
from .cards import cards_from_accounts
from .sandbox_demo import DEMO_ITEMS, custom_user_password

router = APIRouter(prefix="/api/plaid")

# connection id -> access token. In memory: fine for a hackathon demo, lost on restart.
_CONNECTIONS: dict[str, str] = {}


class ExchangeRequest(BaseModel):
    public_token: str
    institution_name: str | None = None  # from Link's onSuccess metadata


def _require_configured() -> None:
    if not client.configured():
        raise HTTPException(503, "Plaid is not configured: set PLAID_CLIENT_ID and PLAID_SECRET in backend/.env")


def _connect(public_token: str, institution: str | None) -> dict:
    access_token, _item_id = client.exchange_public_token(public_token)
    connection_id = secrets.token_urlsafe(12)
    _CONNECTIONS[connection_id] = access_token
    return {"connection_id": connection_id, "cards": cards_from_accounts(client.get_accounts(access_token), institution)}


def _plaid_call(fn, *args):
    try:
        return fn(*args)
    except client.PlaidError as e:
        raise HTTPException(502, str(e)) from e


@router.get("/status")
def status() -> dict:
    return {"configured": client.configured(), "env": client.plaid_env()}


@router.post("/link_token")
def link_token() -> dict:
    _require_configured()
    return {"link_token": _plaid_call(client.create_link_token, secrets.token_hex(8))}


@router.post("/exchange")
def exchange(req: ExchangeRequest) -> dict:
    _require_configured()
    return _plaid_call(_connect, req.public_token, req.institution_name)


@router.post("/sandbox_demo")
def sandbox_demo() -> dict:
    """Connect the demo cards through Sandbox's API (no Link UI). Sandbox only."""
    _require_configured()
    if client.plaid_env() != "sandbox":
        raise HTTPException(400, "The demo connection only runs in the Plaid Sandbox")
    cards = []
    for institution_id, issuer, accounts in DEMO_ITEMS:
        public_token = _plaid_call(
            client.sandbox_public_token, institution_id, "user_custom", custom_user_password(accounts)
        )
        connected = _plaid_call(_connect, public_token, None)
        cards += [{**c, "stands_in_for": issuer} for c in connected["cards"]]
    return {"cards": cards, "sandbox": True}
