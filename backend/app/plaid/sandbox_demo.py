"""Sandbox demo profile: the issuers' own Plaid institution records with a custom test user
whose credit cards carry real product names: https://plaid.com/docs/sandbox/user-custom/

Plaid returns the institution names itself. Production Plaid returns the issuer's own account names.
"""

import json


def _card(name: str, mask: str, balance: int) -> dict:
    return {
        "type": "credit",
        "subtype": "credit card",
        "starting_balance": balance,
        "meta": {"name": name, "official_name": name, "mask": mask},
        "liability": {"type": "credit", "purchase_apr": 24.99, "minimum_payment_amount": 35},
    }


# (Plaid institution id, cards). IDs from /institutions/search: American Express, Chase, Capital One.
DEMO_ITEMS = [
    ("ins_10", [_card("American Express Gold Card", "1005", 1240)]),
    ("ins_56", [_card("Chase Sapphire Preferred", "4417", 860), _card("United Explorer Card", "9023", 310)]),
    ("ins_128026", [_card("Capital One Venture Rewards", "7788", 540)]),
]


def custom_user_password(cards: list[dict]) -> str:
    """The custom user's config JSON is passed as the password with username user_custom."""
    return json.dumps({"override_accounts": cards})
