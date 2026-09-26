# Pointfolio (HackGT 13)

Award tools optimize one flight. Pointfolio optimizes your whole year of points.

## Layout

- `backend/`: FastAPI. Sample redemption dataset in `app/data/redemptions.json`. Optimizer (OR-Tools CP-SAT integer program) in `app/optimizer.py`; explanations and API shaping in `app/planning.py`.
- `frontend/`: Vite + React + TypeScript. Flow: connect cards (mock Plaid) → balances + trips → optimize → Greedy vs. Pointfolio dashboard + Sankey → mock Visa checkout for cash legs.

## Run locally

```bash
cd backend && uv venv .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:5173 (Vite proxies `/api` to `:8000`).

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q
```

## Status

| Piece | State |
|---|---|
| Greedy vs. portfolio optimizer | Real: exact integer program (OR-Tools CP-SAT); greedy = same model, one trip at a time |
| Redemption dataset | Sample/placeholder prices, needs verification. Reserve value (1.0¢/pt) is an assumption |
| Plaid Link (Sandbox) | UI mock only |
| NL trip parse (LLM) | Mock: loads sample trips |
| ElevenLabs voice agent + RAG | Not connected |
| Visa FX Rates API | Not connected |
| Visa checkout (cash leg) | UI mock; no payment is ever processed (by design) |
