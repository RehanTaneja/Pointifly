"""Cash fares per (trip, cabin): from the saved snapshot, or fetched live on demand.

Every live fetch is saved (snapshot + raw response), so each (trip, date, cabin) search
spends SerpApi quota at most once.
"""

import json
from datetime import datetime, timezone

from .data_store import DATA_DIR, SNAPSHOT_PATH, load_dataset
from .sources import serpapi_flights
from .sources.http import env

RAW_DIR = DATA_DIR / "raw"  # full API responses (git-ignored) so re-parsing never spends quota
SOURCE = "Google Flights via SerpApi"
DEFAULT_DAILY_LIMIT = 20  # live searches per UTC day from the app (override with SERPAPI_DAILY_LIMIT)


class SearchBudgetExceeded(Exception):
    pass


def _usage_path():
    return RAW_DIR / "serpapi_usage.json"


def searches_today() -> int:
    p = _usage_path()
    usage = json.loads(p.read_text()) if p.exists() else {}
    return usage.get(now()[:10], 0)


def _record_search() -> None:
    RAW_DIR.mkdir(exist_ok=True)
    p = _usage_path()
    usage = json.loads(p.read_text()) if p.exists() else {}
    day = now()[:10]
    _usage_path().write_text(json.dumps({day: usage.get(day, 0) + 1}))


def daily_limit() -> int:
    return int(env("SERPAPI_DAILY_LIMIT") or DEFAULT_DAILY_LIMIT)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fare_key(trip_id: str, cabin: str) -> str:
    return f"{trip_id}:{cabin}"


def raw_path(key: str):
    return RAW_DIR / f"serpapi_{key.replace(':', '_')}.json"


def read_snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text()) if SNAPSHOT_PATH.exists() else {}


def write_snapshot(snap: dict) -> None:
    SNAPSHOT_PATH.write_text(json.dumps(snap, indent=2) + "\n")
    load_dataset.cache_clear()


def fetch(trip: dict, cabin: str, api_key: str) -> tuple[dict | None, str]:
    """One live search. Returns (fare or None, fetched_at) and saves the raw response."""
    params = serpapi_flights.build_params(trip, cabin)
    response, fetched_at = serpapi_flights.search(params, api_key), now()
    RAW_DIR.mkdir(exist_ok=True)
    raw_path(fare_key(trip["id"], cabin)).write_text(
        json.dumps({"params": params, "fetched_at": fetched_at, "response": response})
    )
    return serpapi_flights.lowest_fare(response, cabin), fetched_at


def entry(fare: dict, fetched_at: str, params: dict) -> dict:
    return {**fare, "source": SOURCE, "fetched_at": fetched_at, "params": params}


def get_fare(trip: dict, cabin: str, live: bool = True) -> dict | None:
    """Saved fare for this trip's current search, else a live fetch when a key is configured."""
    key = fare_key(trip["id"], cabin)
    params = serpapi_flights.build_params(trip, cabin)
    saved = read_snapshot().get("cash_fares", {}).get(key)
    if saved and saved.get("params") == params:
        return saved
    api_key = env("SERPAPI_KEY")
    if not live or not api_key:
        return None
    if searches_today() >= daily_limit():
        raise SearchBudgetExceeded(f"Daily live-search limit reached ({daily_limit()}); saved fares still work")
    _record_search()
    fare, fetched_at = fetch(trip, cabin, api_key)
    if fare is None:
        return None
    snap = read_snapshot()
    snap.setdefault("cash_fares", {})[key] = entry(fare, fetched_at, params)
    write_snapshot(snap)
    return snap["cash_fares"][key]
