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

## Real data (free tiers)

Copy `backend/.env.example` to `backend/.env` and add keys, then:

```bash
cd backend && .venv/bin/python -m app.sources.refresh --dry-run
```

```bash
cd backend && .venv/bin/python -m app.sources.refresh --fares
```

Results are saved to `backend/app/data/snapshots.json` (with source + fetch time) and overlaid on the sample dataset; anything not fetched stays sample. Choosing a new cabin in the UI fetches that fare once and saves it. `--reparse` re-reads saved responses without spending searches.

| Data | Source | Free tier |
|---|---|---|
| Cash fares (live) | Google Flights via [SerpApi](https://serpapi.com/google-flights-api) | 100 searches/month; a full refresh uses 7 |
| Transfer partners + ratios | Official issuer pages, curated in `backend/app/data/transfer_ratios.json` (verified 2026-09-26): [Amex](https://global.americanexpress.com/rewards/transfer?tier=MR), [Chase](https://www.chase.com/sapphire-cards/personal/preferred), [Capital One](https://www.capitalone.com/learn-grow/money-management/venture-miles-transfer-partnerships/) | Free; re-verify before the demo |
| Award prices (points) | No free live source found | Still sample |

Not usable: Amadeus Self-Service (shut down July 17, 2026), ITA Matrix (no public API), Seats.aero (paid Pro plan, non-commercial).

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q
```

## Status

| Piece | State |
|---|---|
| Greedy vs. portfolio optimizer | Real: exact integer program (OR-Tools CP-SAT); greedy = same model, one trip at a time |
| Redemption dataset | Sample award prices. Live cash fares; official transfer ratios. Reserve value (1.0¢/pt) is an assumption |
| Plaid Link (Sandbox) | UI mock only |
| NL trip parse (LLM) | Mock: loads sample trips |
| ElevenLabs voice agent + RAG | Not connected |
| Visa FX Rates API | Not connected |
| Visa checkout (cash leg) | UI mock; no payment is ever processed (by design) |
