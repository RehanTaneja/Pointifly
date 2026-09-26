import copy
import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_PATH = DATA_DIR / "redemptions.json"
SNAPSHOT_PATH = DATA_DIR / "snapshots.json"


def load_base_dataset() -> dict:
    with DATA_PATH.open() as f:
        return json.load(f)


def apply_snapshot(ds: dict, snap: dict) -> dict:
    """Overlay fetched real data on the sample dataset. Anything not fetched keeps its sample value."""
    ds = copy.deepcopy(ds)
    fares = snap.get("cash_fares", {})
    for trip in ds["sample_trips"]:
        base = fares.get(f"{trip['id']}:{trip['cabin']}")
        if base:
            trip["cash_price_usd"] = base["price"]
            trip["cash_source"] = {"source": base["source"], "fetched_at": base["fetched_at"]}
        for opt in trip["award_options"]:
            other = fares.get(f"{trip['id']}:{opt['cabin']}") if "cabin" in opt else None
            if other:
                opt["cash_price_usd"] = other["price"]

    transfers = snap.get("transfers")
    if transfers:
        programs = {p["id"] for p in ds["programs"]}
        for cur in ds["currencies"]:
            fetched = transfers["ratios"].get(cur["id"])
            if fetched is not None:
                cur["transfers"] = {p: r for p, r in fetched.items() if p in programs}
                cur["transfers_source"] = {"source": transfers["source"], "fetched_at": transfers["fetched_at"]}
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
