from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .data_store import load_dataset
from .mock_optimizer import optimize_mock
from .models import OptimizeRequest, OptimizeResponse

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
def optimize(_req: OptimizeRequest | None = None) -> OptimizeResponse:
    # TODO: replace with real greedy + portfolio solvers. Input is ignored for now.
    return optimize_mock()
