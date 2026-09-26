from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .data_store import holding_names, load_dataset
from .models import OptimizeRequest, OptimizeResponse
from .planning import Planner
from .ai.routes import router as ai_router
from .plaid.routes import router as plaid_router
from .visa.routes import router as visa_router
from . import card_rewards
from .charts import airports
from .trips import CABINS, MAX_TRIPS, FareUnavailable, custom_trip, effective_trip

app = FastAPI(title="Pointifly API")
app.include_router(plaid_router)
app.include_router(visa_router)
app.include_router(ai_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/dataset")
def dataset() -> dict:
    return load_dataset()


@app.post("/api/optimize", response_model=OptimizeResponse)
def optimize(req: OptimizeRequest | None = None) -> OptimizeResponse:
    """Greedy vs. portfolio over the given balances and trips (defaults: sample data)."""
    req = req or OptimizeRequest()
    unknown = [c for c in req.cards or [] if c not in card_rewards.cards()]
    if unknown:
        raise HTTPException(400, f"Unknown card products: {unknown}")
    return Planner(*_inputs(req, load_dataset()), card_ids=req.cards).run()


def _inputs(req: OptimizeRequest, ds: dict) -> tuple[list[dict], dict[str, int]]:
    known = holding_names()
    balances = {b.holding: b.points for b in req.balances} or {
        b["holding"]: b["points"] for b in ds["sample_balances"]
    }
    unknown = [h for h in balances if h not in known]
    if unknown or any(v < 0 for v in balances.values()):
        raise HTTPException(400, f"Invalid balances: unknown holdings {unknown}" if unknown else "Negative balance")

    trips_by_id = {t["id"]: t for t in ds["sample_trips"]}
    ids = req.trip_ids or ([] if req.custom_trips else list(trips_by_id))
    missing = [i for i in ids if i not in trips_by_id]
    if missing:
        raise HTTPException(400, f"Unknown trips: {missing}")
    bad = {t: c for t, c in req.cabins.items() if c not in CABINS or t not in trips_by_id}
    if bad:
        raise HTTPException(400, f"Invalid cabins: {bad} (choose from {CABINS})")
    try:
        customs = [custom_trip(c.origin, c.destination, c.date, c.cabin, c.label) for c in req.custom_trips]
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if len(ids) + len(customs) > MAX_TRIPS:
        raise HTTPException(400, f"At most {MAX_TRIPS} trips per plan")
    if len({c["id"] for c in customs}) < len(customs):
        raise HTTPException(400, "The same trip was added twice")
    try:
        trips = [effective_trip(trips_by_id[i], req.cabins.get(i, trips_by_id[i]["cabin"])) for i in ids]
        trips += [effective_trip(c, c["cabin"]) for c in customs]
    except FareUnavailable as e:
        raise HTTPException(422, str(e)) from e
    return trips, balances


@app.get("/api/airports")
def airport_search(q: str = "", limit: int = 8) -> list[dict]:
    """IATA code, city or airport-name search for the trip form."""
    q = q.strip().lower()
    if len(q) < 2:
        return []
    exact, starts, contains = [], [], []
    for code, (name, country, _region, _lat, _lon, city) in airports().items():
        row = {"code": code, "name": name, "city": city, "country": country}
        if code.lower() == q:
            exact.append(row)
        elif code.lower().startswith(q) or city.lower().startswith(q):
            starts.append(row)
        elif q in name.lower() or q in city.lower():
            contains.append(row)
    return (exact + starts + contains)[: max(1, min(limit, 20))]
