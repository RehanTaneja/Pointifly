"""Fetch real data and save it to app/data/snapshots.json.

  python -m app.sources.refresh --dry-run     # show planned calls, no keys needed
  python -m app.sources.refresh --fares       # SERPAPI_KEY: live Google Flights cash fares
  python -m app.sources.refresh --fares --force   # re-fetch even fares fetched recently
  python -m app.sources.refresh --reparse     # re-read saved raw responses: no API calls, no key
  python -m app.sources.refresh --transfers   # REWARDSCC_KEY: transfer partners + ratios

Snapshots keep the demo working offline and stretch SerpApi's 100 free searches/month.
"""

import argparse
import json
from datetime import datetime, timedelta, timezone

from ..data_store import DATA_DIR, SNAPSHOT_PATH, load_base_dataset
from . import rewardscc, serpapi_flights
from .http import env


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fare_searches(ds: dict) -> list[tuple[str, dict, dict]]:
    """One search per (trip, cabin) the optimizer needs a cash value for."""
    out = []
    for trip in ds["sample_trips"]:
        cabins = {trip["cabin"]} | {o["cabin"] for o in trip["award_options"] if "cabin" in o}
        for cabin in sorted(cabins):
            out.append((f"{trip['id']}:{cabin}", trip, serpapi_flights.build_params(trip, cabin)))
    return out


FRESH_FOR = timedelta(days=3)
RAW_DIR = DATA_DIR / "raw"  # full API responses (git-ignored) so re-parsing never spends quota


def is_fresh(entry: dict | None, params: dict) -> bool:
    """Fetched recently with the same search, so re-fetching would only spend quota."""
    if not entry or entry.get("params") != params:
        return False
    return datetime.now(timezone.utc) - datetime.fromisoformat(entry["fetched_at"]) < FRESH_FOR


def refresh_fares(ds: dict, snap: dict, api_key: str | None, force: bool = False, reparse: bool = False) -> None:
    fares = snap.setdefault("cash_fares", {})
    for key, trip, params in fare_searches(ds):
        cabin = key.split(":")[1]
        raw_path = RAW_DIR / f"serpapi_{key.replace(':', '_')}.json"
        if reparse:
            raw = json.loads(raw_path.read_text()) if raw_path.exists() else None
            if not raw or raw["params"] != params:
                print(f"  {key}: no saved response for this search, skipping")
                continue
            response, fetched_at = raw["response"], raw["fetched_at"]
        elif not force and is_fresh(fares.get(key), params):
            print(f"  {key}: fetched {fares[key]['fetched_at'][:10]}, skipping (use --force to re-fetch)")
            continue
        else:
            response, fetched_at = serpapi_flights.search(params, api_key), _now()
            RAW_DIR.mkdir(exist_ok=True)
            raw_path.write_text(json.dumps({"params": params, "fetched_at": fetched_at, "response": response}))
        fare = serpapi_flights.lowest_fare(response, cabin)
        if fare is None:
            fares.pop(key, None)
            print(f"  {key}: no itinerary fully in {cabin}, using sample value")
            continue
        fares[key] = {**fare, "source": "Google Flights via SerpApi", "fetched_at": fetched_at, "params": params}
        print(f"  {key}: ${fare['price']} ({', '.join(fare['airlines'])})")


def refresh_transfers(ds: dict, snap: dict, api_key: str, force: bool = False) -> None:
    ours = {p["id"]: p["match"] for p in ds["programs"]}
    wanted = {}
    for row in rewardscc.transfer_programs(api_key):
        name = row["transferPartnerName"].lower()
        for pid, needles in ours.items():
            if any(n in name for n in needles):
                wanted[pid] = row
    print(f"  matched {len(wanted)}/{len(ours)} programs: {sorted(wanted)}")
    rows = {pid: rewardscc.program_cards(row["transferPartnerId"], api_key) for pid, row in wanted.items()}
    snap["transfers"] = {"source": "RewardsCC", "fetched_at": _now(), "ratios": rewardscc.ratios(rows)}
    print(f"  ratios: {json.dumps(snap['transfers']['ratios'])}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fares", action="store_true")
    ap.add_argument("--transfers", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-fetch fares fetched in the last 3 days")
    ap.add_argument("--reparse", action="store_true", help="re-parse saved raw responses without API calls")
    args = ap.parse_args()
    ds = load_base_dataset()

    if args.dry_run:
        searches = fare_searches(ds)
        print(f"--fares would use {len(searches)} SerpApi searches:")
        for key, _, params in searches:
            print(f"  {key}: {params}")
        print(f"--transfers would make 1 + (matched programs, up to {len(ds['programs'])}) RewardsCC calls")
        return

    snap = json.loads(SNAPSHOT_PATH.read_text()) if SNAPSHOT_PATH.exists() else {}
    if args.reparse:
        print("refresh_fares (reparse):")
        refresh_fares(ds, snap, None, reparse=True)
    for flag, name, fn in ((args.fares, "SERPAPI_KEY", refresh_fares), (args.transfers, "REWARDSCC_KEY", refresh_transfers)):
        if not flag:
            continue
        key = env(name)
        if not key:
            raise SystemExit(f"{name} is not set (add it to backend/.env)")
        print(f"{fn.__name__}:")
        fn(ds, snap, key, force=args.force)
    SNAPSHOT_PATH.write_text(json.dumps(snap, indent=2) + "\n")
    print(f"saved {SNAPSHOT_PATH}")


if __name__ == "__main__":
    main()
