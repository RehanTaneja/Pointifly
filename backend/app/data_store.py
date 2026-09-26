import json
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).parent / "data" / "redemptions.json"


@lru_cache
def load_dataset() -> dict:
    with DATA_PATH.open() as f:
        return json.load(f)


def holding_names() -> dict[str, str]:
    """id -> display name for every currency and program a user can hold."""
    ds = load_dataset()
    return {c["id"]: c["name"] for c in ds["currencies"]} | {
        p["id"]: p["name"] for p in ds["programs"]
    }
