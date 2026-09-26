"""Minimal Plaid API client (stdlib HTTP). Docs: https://plaid.com/docs/api/

Keys come from backend/.env: PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ENV (default "sandbox").
Sandbox is free with unlimited test Items: https://plaid.com/docs/sandbox/
"""

import json
import urllib.error
import urllib.request

from ..sources.http import env

BASE_URLS = {"sandbox": "https://sandbox.plaid.com", "production": "https://production.plaid.com"}


class PlaidError(Exception):
    def __init__(self, status: int, body: dict):
        self.status, self.body = status, body
        super().__init__(f"Plaid {status}: {body.get('error_code')} {body.get('error_message')}")


def plaid_env() -> str:
    return (env("PLAID_ENV") or "sandbox").lower()


def configured() -> bool:
    return bool(env("PLAID_CLIENT_ID") and env("PLAID_SECRET")) and plaid_env() in BASE_URLS


def post(path: str, body: dict) -> dict:
    payload = {"client_id": env("PLAID_CLIENT_ID"), "secret": env("PLAID_SECRET"), **body}
    req = urllib.request.Request(
        BASE_URLS[plaid_env()] + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise PlaidError(e.code, json.loads(e.read() or b"{}")) from e


def create_link_token(client_user_id: str) -> str:
    """https://plaid.com/docs/api/link/#linktokencreate"""
    return post(
        "/link/token/create",
        {
            "client_name": "Pointfolio",
            "language": "en",
            "country_codes": ["US"],
            "user": {"client_user_id": client_user_id},
            # Credit cards are what we need; liabilities limits Link to institutions that have them.
            "products": [env("PLAID_PRODUCT") or "liabilities"],
        },
    )["link_token"]


def exchange_public_token(public_token: str) -> tuple[str, str]:
    """https://plaid.com/docs/api/items/#itempublic_tokenexchange -> (access_token, item_id)"""
    r = post("/item/public_token/exchange", {"public_token": public_token})
    return r["access_token"], r["item_id"]


def get_accounts(access_token: str) -> dict:
    """https://plaid.com/docs/api/accounts/#accountsget -> {accounts: [...], item: {...}}"""
    return post("/accounts/get", {"access_token": access_token})


def sandbox_public_token(institution_id: str, override_username: str, override_password: str) -> str:
    """Sandbox only, skips the Link UI: https://plaid.com/docs/api/sandbox/#sandboxpublic_tokencreate"""
    return post(
        "/sandbox/public_token/create",
        {
            "institution_id": institution_id,
            "initial_products": [env("PLAID_PRODUCT") or "liabilities"],
            "options": {"override_username": override_username, "override_password": override_password},
        },
    )["public_token"]
