"""Sandbox demo: custom test users whose credit cards carry real product names.

Plaid Sandbox has only test banks (e.g. First Platypus Bank), so each "issuer" below is a
Sandbox test institution with a custom user: https://plaid.com/docs/sandbox/user-custom/
Card names are ours; production Plaid returns the issuer's own account names.
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


# (Sandbox institution id, the issuer these test cards stand in for, cards)
DEMO_ITEMS = [
    ("ins_109508", "American Express", [_card("American Express Gold Card", "1005", 1240)]),
    ("ins_109509", "Chase", [_card("Chase Sapphire Preferred", "4417", 860), _card("United Explorer Card", "9023", 310)]),
    ("ins_109510", "Capital One", [_card("Capital One Venture Rewards", "7788", 540)]),
]


def custom_user_password(cards: list[dict]) -> str:
    """The custom user's config JSON is passed as the password with username user_custom."""
    return json.dumps({"override_accounts": cards})
