import copy
import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_PATH = DATA_DIR / "redemptions.json"
SNAPSHOT_PATH = DATA_DIR / "snapshots.json"
RATIOS_PATH = DATA_DIR / "transfer_ratios.json"


def load_base_dataset() -> dict:
    """Sample dataset with each currency's official transfer partners and ratios merged in."""
    with DATA_PATH.open() as f:
        ds = json.load(f)
    with RATIOS_PATH.open() as f:
        ratios = json.load(f)
    for cur in ds["currencies"]:
        issuer = ratios["issuers"][cur["id"]]
        cur["transfers"] = {pid: d["ratio"] for pid, d in issuer["partners"].items()}
        cur["transfer_details"] = issuer["partners"]
        cur["transfer_source"] = {
            "url": issuer["source_url"],
            "title": issuer["source_title"],
            "eligibility": issuer["eligibility"],
            "verified_on": ratios["verified_on"],
        }
    return ds


def apply_snapshot(ds: dict, snap: dict) -> dict:
    """Overlay fetched real data on the sample dataset. Anything not fetched keeps its sample value."""
    ds = copy.deepcopy(ds)
    fares = snap.get("cash_fares", {})
    for trip in ds["sample_trips"]:
        # Every cabin already fetched for this trip, so the UI can show prices before optimizing.
        trip["cash_fares"] = {
            k.split(":")[1]: {"price": v["price"], "fetched_at": v["fetched_at"]}
            for k, v in fares.items()
            if k.split(":")[0] == trip["id"]
        }
        base = fares.get(f"{trip['id']}:{trip['cabin']}")
        if base:
            trip["cash_price_usd"] = base["price"]
            trip["cash_source"] = {"source": base["source"], "fetched_at": base["fetched_at"]}
        for opt in trip["award_options"]:
            other = fares.get(f"{trip['id']}:{opt['cabin']}") if "cabin" in opt else None
            if other:
                opt["cash_price_usd"] = other["price"]
    return ds


@lru_cache
def load_dataset() -> dict:
    ds = load_base_dataset()
    if SNAPSHOT_PATH.exists():
        ds = apply_snapshot(ds, json.loads(SNAPSHOT_PATH.read_text()))
    return ds


def holding_names() -> dict[str, str]:
    """id -> display name for every currency and program a user can hold."""
    ds = load_dataset()
    return {c["id"]: c["name"] for c in ds["currencies"]} | {
        p["id"]: p["name"] for p in ds["programs"]
    }
