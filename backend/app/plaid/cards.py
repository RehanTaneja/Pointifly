"""Map a card's name (from Plaid) to the points currency or airline program it earns."""

import re

from ..card_rewards import product_id

# (pattern on the card's official_name or name, holding id, note). First match wins, so the
# more specific patterns (co-branded cards) come before the issuer's general points cards.
RULES: list[tuple[str, str | None, str | None]] = [
    # Co-branded cards earn the partner's own currency, not the issuer's transferable points.
    (r"\b(delta|skymiles|hilton|marriott|bonvoy|hyatt|ihg|southwest|british airways|jetblue)\b", None,
     "Co-branded card: earns a program Pointifly doesn't model yet."),
    (r"\baeroplan\b", "aeroplan", None),
    (r"\bunited\b", "united", None),
    (r"\bsapphire (preferred|reserve)\b|\bink business preferred\b", "chase_ur", None),
    (r"\bfreedom\b|\bink business (cash|unlimited)\b", "chase_ur",
     "Earns Ultimate Rewards, but transfers need Sapphire Preferred, Sapphire Reserve or Ink Business Preferred."),
    (r"\bventure(one| x)?\b|\bspark miles\b", "capital_one", None),
    (r"\b(platinum|gold|green) card\b|\bamex everyday\b|\bblue business plus\b", "amex_mr", None),
]


def classify(account: dict) -> tuple[str | None, str | None]:
    """(holding id or None, note). Matches the official name and the account name."""
    text = " ".join(filter(None, [account.get("official_name"), account.get("name")])).lower()
    for pattern, holding, note in RULES:
        if re.search(pattern, text):
            return holding, note
    return None, None


def cards_from_accounts(accounts_response: dict, institution: str | None = None) -> list[dict]:
    """Credit cards from an /accounts/get response, each mapped to a holding where we can."""
    item = accounts_response.get("item") or {}
    inst = institution or item.get("institution_name") or item.get("institution_id") or "Unknown institution"
    out = []
    for acct in accounts_response.get("accounts", []):
        if acct.get("type") != "credit":
            continue
        holding, note = classify(acct)
        name = acct.get("official_name") or acct.get("name") or ""
        out.append(
            {
                "product_id": product_id(name),
                "account_id": acct.get("account_id"),
                "institution": inst,
                "product": acct.get("official_name") or acct.get("name") or "Credit card",
                "mask": acct.get("mask"),
                "holding": holding,
                "note": note,
            }
        )
    return out
