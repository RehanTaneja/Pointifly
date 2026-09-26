# Pointfolio (HackGT 13)

Award tools optimize one flight. Pointfolio optimizes your whole year of points.

Connect your cards, enter your point balances and trips, and Pointfolio decides for every trip whether to pay cash or which points to transfer where, so the whole year gets the most value. It shows the result next to a trip-by-trip ("greedy") plan to make the difference visible.

## How the optimizer works

Not ML or AI. It's a **mathematical optimization model** (an integer program) solved exactly with Google OR-Tools CP-SAT:

- **Choices:** each trip is paid in cash or with one award option; each award is funded by points from one or more cards.
- **Rules:** one payment per trip; transferred points (after the transfer ratio, in the bank's transfer blocks) must cover the award; no balance is overdrawn.
- **Score:** value of the awards booked, minus award fees, minus a 1.0¢ "reserve value" for every point spent (an award only wins if it beats keeping the points).
- The solver searches all combinations but proves whole groups of them can't win and skips them, so the answer is **provably the best** plan under these rules.
- **Greedy** is the same model solved one trip at a time in date order, which is what per-flight tools do.

Code: `backend/app/optimizer.py` (model), `backend/app/planning.py` (explanations, API response).

## Layout

- `backend/`: FastAPI + OR-Tools. Data in `backend/app/data/`, integrations in `app/plaid/`, `app/visa/`, `app/sources/`.
- `frontend/`: Vite + React + TypeScript. Flow: connect cards (Plaid) → balances + trips (cabin per trip) → optimize → Greedy vs. Pointfolio dashboard, Sankey, flight details, Visa travel benefits → Visa checkout for cash legs.

## Run locally

```bash
cd backend && uv venv .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:5173 (Vite proxies `/api` to `:8000`). Copy `backend/.env.example` to `backend/.env` for the integrations below; everything falls back to cached or sample data without keys.

## Data sources

| Data | Source | Notes |
|---|---|---|
| Cash fares | Google Flights via [SerpApi](https://serpapi.com/google-flights-api) | Live. Snapshot in `app/data/snapshots.json`; only full-cabin itineraries count. A new cabin choice is fetched once and saved |
| Award prices | Official charts in `app/data/award_charts.json`: [Aeroplan 2026-08](https://www.aircanada.com/content/dam/aircanada/loyalty-content/documents/flight-rewards-chart-en.pdf) ("all other partners") and [ANA one-way partner chart](https://www.ana.co.jp/en/jp/guide/amc/award/tk/zone/) | Published prices: award seat availability isn't checked. Other programs use sample prices |
| Transfer partners + ratios | Official issuer pages in `app/data/transfer_ratios.json` (verified 2026-09-26): [Amex](https://global.americanexpress.com/rewards/transfer?tier=MR), [Chase](https://www.chase.com/sapphire-cards/personal/preferred), [Capital One](https://www.capitalone.com/learn-grow/money-management/venture-miles-transfer-partnerships/) | Includes minimums, transfer blocks, transfer times |
| Card detection | [Plaid](https://plaid.com/docs/) (Sandbox) | Card names map to points programs; balances stay manual (Plaid doesn't expose rewards points) |
| Exchange rates | [Visa Foreign Exchange Rates](https://developer.visa.com/capabilities/foreign_exchange) (Sandbox) | Converts Aeroplan's $39 CAD partner booking fee into the plan; shows destination-currency rates |
| Travel benefits | [Visa Merchant Offers Resource Center](https://developer.visa.com/capabilities/vmorc) (Sandbox) | Display only (card benefits, not flight prices) |
| Airports | [OurAirports](https://ourairports.com/data/) (public domain) | Great-circle distance and zones for the award charts |

## Keys (`backend/.env`)

See `backend/.env.example`. Never commit `.env`; certificates and keys go in `backend/secrets/` (git-ignored).

- **SerpApi:** `SERPAPI_KEY` (free plan). Refresh fares with `.venv/bin/python -m app.sources.refresh --fares` (skips fares fetched in the last 3 days; `--dry-run` shows the searches; `--reparse` re-reads saved responses without API calls).
- **Plaid:** `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV=sandbox` from https://dashboard.plaid.com. The demo profile connects American Express, Chase and Capital One (Plaid's own institution records) with cards named after real products. `PRESENTATION_MODE=1` shows a single Connect with Plaid button with no environment tags or developer controls.
- **Visa:** a Visa Developer project with Foreign Exchange Rates and Merchant Offers Resource Center. Two-way SSL: download the certificate and private key to `backend/secrets/`, then set `VISA_USER_ID`, `VISA_PASSWORD` (the project's Two-Way SSL credentials, not your account password), `VISA_CERT_PATH`, `VISA_KEY_PATH`.

### API usage limits

- **SerpApi:** 250 searches/month on the free plan; a full refresh of the sample trips uses 7.
- **Visa:** at most one FX call per currency pair per day and one offers call per day, cached in `app/data/visa_fx_rates.json` and `app/data/visa_offers.json` (committed, so the demo works offline). If Visa is unreachable the last cached value is used, with its date. Sandbox FX rates appear to be sample values, not current market rates.
- **Tests never call Visa:** `backend/tests/conftest.py` replaces the Visa client with a fake for every test.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q
```

The live Plaid Sandbox test runs when Plaid keys are set; all other external APIs are faked.

## Status

| Piece | State |
|---|---|
| Greedy vs. portfolio optimizer | Built (exact integer program, OR-Tools CP-SAT) |
| Cash fares, cabin choice, flight details + Google Flights links | Built (SerpApi) |
| Award prices | Aeroplan + ANA from official charts; other programs sample |
| Transfer ratios | Built (official issuer pages) |
| Plaid card detection | Built (Sandbox), presentation mode for the pitch |
| Visa FX | Built (Sandbox): fee conversion in the plan, destination rates in the UI |
| Visa travel benefits (VMORC) | Built (Sandbox), display only |
| Visa checkout for cash legs | UI mock; no payment is processed |
| Trip parsing from a sentence (LLM) | Not built (mock loads sample trips) |
| ElevenLabs voice agent + knowledge base | Not built |
