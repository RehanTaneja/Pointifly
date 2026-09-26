"""Transfer partners and ratios from the Rewards Credit Card API (sold via RapidAPI).

Docs: https://rewardscc.com/docs/get-credit-card/point-transfer/transfer-program-list
The RapidAPI host below follows RapidAPI's standard naming; override with REWARDSCC_HOST
if the API's RapidAPI page shows a different one.
"""

from .http import env, get_json

DEFAULT_HOST = "rewards-credit-card-api.p.rapidapi.com"

# Our currency ids -> text that identifies them in RewardsCC's rewardProgramName.
CURRENCY_MATCH = {
    "amex_mr": "membership rewards",
    "chase_ur": "ultimate rewards",
    "capital_one": "capital one",
}


def _host() -> str:
    return env("REWARDSCC_HOST") or DEFAULT_HOST


def _get(path: str, api_key: str):
    host = _host()
    return get_json(f"https://{host}{path}", headers={"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": host})


def transfer_programs(api_key: str) -> list[dict]:
    """[{transferPartnerName, transferPartnerId}, ...]"""
    return _get("/creditcard-pointtransfer-transferprogramlist/", api_key)


def program_cards(partner_id: str | int, api_key: str) -> list[dict]:
    """Cards that transfer to this partner, each with rewardProgramName and transferRatio."""
    return _get(f"/creditcard-pointtransfer-transferprogramcard/{partner_id}", api_key)


def ratios(partner_rows: dict[str, list[dict]]) -> dict[str, dict[str, float]]:
    """{program id: card rows} -> {our currency id: {program id: base transfer ratio}}.

    Uses transferRatio (bonus excluded): temporary bonuses shouldn't change the plan.
    """
    out: dict[str, dict[str, float]] = {}
    for partner, rows in partner_rows.items():
        for row in rows:
            program = (row.get("rewardProgramName") or "").lower()
            for cid, needle in CURRENCY_MATCH.items():
                if needle in program and row.get("transferRatio"):
                    out.setdefault(cid, {})[partner] = float(row["transferRatio"])
    return out
