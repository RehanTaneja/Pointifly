from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .data_store import holding_names, load_dataset
from .models import OptimizeRequest, OptimizeResponse
from .planning import Planner

app = FastAPI(title="Pointfolio API")

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
    return Planner(*_inputs(req or OptimizeRequest(), load_dataset())).run()


def _inputs(req: OptimizeRequest, ds: dict) -> tuple[list[dict], dict[str, int]]:
    known = holding_names()
    balances = {b.holding: b.points for b in req.balances} or {
        b["holding"]: b["points"] for b in ds["sample_balances"]
    }
    unknown = [h for h in balances if h not in known]
    if unknown or any(v < 0 for v in balances.values()):
        raise HTTPException(400, f"Invalid balances: unknown holdings {unknown}" if unknown else "Negative balance")

    trips_by_id = {t["id"]: t for t in ds["sample_trips"]}
    ids = req.trip_ids or list(trips_by_id)
    missing = [i for i in ids if i not in trips_by_id]
    if missing:
        raise HTTPException(400, f"Unknown trips: {missing}")
    return [trips_by_id[i] for i in ids], balances
