"""ElevenLabs voice agent: signed sessions, knowledge base (RAG) text, and one-time agent setup.

Privacy design:
- The API key stays on the server; the browser gets a 15-minute signed URL.
- Tools are *client* tools: they run in the user's browser against the local backend, so
  balances, cards and trips never live on ElevenLabs. The agent only sees tool results.
- The knowledge base holds public reference data only (official ratios, charts, earn rates,
  how the optimizer works). Never user data or credentials.

Setup (creates documents, indexes them, creates tools and the agent; ids are remembered in
app/data/raw/elevenlabs_setup.json so re-runs don't duplicate anything):
  python -m app.ai.voice --dry-run
  python -m app.ai.voice --setup
Docs: https://elevenlabs.io/docs/agents-platform
"""

import argparse
import json
import time
import urllib.error
import urllib.request

from .. import card_rewards
from ..charts import charts
from ..data_store import DATA_DIR, load_base_dataset
from ..sources.http import env

API = "https://api.elevenlabs.io"
SETUP_STATE = DATA_DIR / "raw" / "elevenlabs_setup.json"
RAG_MODEL = "e5_mistral_7b_instruct"


class VoiceUnavailable(Exception):
    pass


def configured() -> bool:
    return bool(env("ELEVENLABS_API_KEY") and env("ELEVENLABS_AGENT_ID"))


def _request(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        API + path,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"xi-api-key": env("ELEVENLABS_API_KEY") or "", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise VoiceUnavailable(f"ElevenLabs {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}") from e


def signed_url() -> str:
    if not configured():
        raise VoiceUnavailable("Voice needs ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID in backend/.env")
    return _request("GET", f"/v1/convai/conversation/get-signed-url?agent_id={env('ELEVENLABS_AGENT_ID')}")["signed_url"]


# --- knowledge base: public reference data only -------------------------------------------


def knowledge_documents() -> dict[str, str]:
    ds = load_base_dataset()
    names = {c["id"]: c["name"] for c in ds["currencies"]} | {p["id"]: p["name"] for p in ds["programs"]}

    ratios = ["Pointifly transfer partners and ratios (official issuer pages, verified 2026-09-26)."]
    for cur in ds["currencies"]:
        src = cur["transfer_source"]
        ratios.append(f"\n{cur['name']} ({src['url']}). {src['eligibility']}")
        for pid, d in cur["transfer_details"].items():
            via = f" via {d['via'].split('.')[0]}" if d.get("via") else ""
            ratios.append(
                f"- {cur['name']} to {names[pid]}{via}: 1,000 points = {int(1000 * d['ratio']):,} "
                f"(minimum {d['minimum']:,}, in blocks of {d['increment']:,}; transfer time: {d['transfer_time'] or 'not published'})."
            )

    c = charts()
    aero, ana = c["aeroplan"], c["ana"]
    chart = [
        f"Award charts Pointifly uses (one-way, partner airlines, points only; seat availability and taxes not included).",
        f"\n{aero['name']}, {aero['source_title']} ({aero['source_url']}). {aero['price_basis']}",
        f"Partner booking fee: {aero['partner_booking_fee']['quoted']}.",
    ]
    for pair, bands in aero["bands"].items():
        zones = " to ".join(z for z in pair.split("|"))
        for i, b in enumerate(bands):
            lo = 0 if i == 0 else bands[i - 1]["max_miles"] + 1
            hi = f"{b['max_miles']:,}" if b["max_miles"] else "and more"
            prices = ", ".join(f"{cab} {b[cab]:,}" for cab in ("economy", "business", "first") if b.get(cab))
            chart.append(f"- Aeroplan {zones} zones, {lo:,}–{hi} miles: {prices} points.")
    chart.append(f"\n{ana['name']}, {ana['source_title']} ({ana['source_url']}). {ana['price_basis']}")
    for pair, row in ana["table"].items():
        a, b = pair.split("|")
        chart.append(f"- ANA zone {a} to zone {b}: economy {row['economy']:,}, business {row['business']:,}, first {row['first']:,} miles.")

    earn = ["Visa card earn rates on airfare paid in cash (official issuer pages, verified 2026-09-26)."]
    for cid, card in card_rewards.cards().items():
        rate = card["airfare"]
        earn.append(
            f"- {card['name']} ({card['network']}{', ' + card['tier'] if card['tier'] else ''}): "
            + (", ".join(f"{k}: {v}x" for k, v in rate.items()) if rate else "not a Visa card; not used for Visa checkout")
            + f". Quote: {card['quoted']}."
        )

    how = (
        "How Pointifly decides. It is a mathematical optimization model (an integer program solved exactly "
        "with Google OR-Tools), not machine learning. For every trip it chooses cash or one award option, and "
        "which cards' points to transfer, subject to: one payment per trip, transfers in the bank's blocks at "
        "official ratios, and never spending more points than you have. It maximizes the value of the awards "
        "booked, minus award fees, minus a 1 cent reserve value for every point spent (an award only wins if it "
        "beats keeping the points), plus points earned paying cash legs with a Visa card. Earned points can pay "
        "for trips at least 30 days later. It compares this whole-year plan with a trip-by-trip (greedy) plan "
        "that uses the same model one trip at a time, which is what per-flight award tools do. Cash fares come "
        "from Google Flights; award prices for Aeroplan and ANA come from their official charts."
    )
    return {
        "Pointifly transfer ratios": "\n".join(ratios),
        "Pointifly award charts": "\n".join(chart),
        "Pointifly Visa card earn rates": "\n".join(earn),
        "How Pointifly decides": how,
    }


# --- agent definition -------------------------------------------------------------------------

CLIENT_TOOLS = [
    {
        "type": "client",
        "name": "fill_trip_plan",
        "description": (
            "Use when the user states point balances and/or upcoming trips. Pass their words verbatim in "
            "'sentence'. Fills the form and returns what was understood."
        ),
        "parameters": {
            "type": "object",
            "properties": {"sentence": {"type": "string", "description": "The user's words, verbatim"}},
            "required": ["sentence"],
        },
        "expects_response": True,
        "response_timeout_secs": 30,
    },
    {
        "type": "client",
        "name": "run_optimizer",
        "description": "Run Pointifly's optimizer on the balances and trips on screen. Returns the plan summary.",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "expects_response": True,
        "response_timeout_secs": 60,
    },
    {
        "type": "client",
        "name": "explain_trip",
        "description": "Explain why the plan pays a given trip with cash or points. Call after run_optimizer.",
        "parameters": {
            "type": "object",
            "properties": {"trip": {"type": "string", "description": "Trip name or destination, e.g. Delhi"}},
            "required": ["trip"],
        },
        "expects_response": True,
        "response_timeout_secs": 20,
    },
]

AGENT_PROMPT = """You are Pointifly's voice assistant. Pointifly plans a traveler's whole year of points.

How to help:
1. Ask for their point balances and trips (where and roughly when; cabin if not economy). When they
   answer, call fill_trip_plan with their exact words, then read back briefly what was understood.
2. When they're ready, call run_optimizer and summarize the plan in two or three sentences: the
   headline value difference, then which trips use points (and which cards to transfer) versus cash.
3. For "why" questions about a trip, call explain_trip. For questions about transfer ratios, award
   charts, card earn rates or how Pointifly decides, answer from the knowledge base.

Rules: never ask for card numbers, passwords, security codes or account logins; balances in points are
fine. Numbers about the plan must come from the tools, never estimated. Keep replies short and spoken."""

FIRST_MESSAGE = "Hi, I'm Pointifly. Tell me your point balances and the trips you're planning this year."


def agent_body(tool_ids: list[str], docs: list[dict]) -> dict:
    return {
        "name": "Pointifly",
        "conversation_config": {
            "agent": {
                "first_message": FIRST_MESSAGE,
                "language": "en",
                "prompt": {
                    "prompt": AGENT_PROMPT,
                    "tool_ids": tool_ids,
                    "knowledge_base": [{"type": "text", "id": d["id"], "name": d["name"], "usage_mode": "auto"} for d in docs],
                    "rag": {"enabled": True, "embedding_model": RAG_MODEL},
                },
            }
        },
    }


def _load_state() -> dict:
    return json.loads(SETUP_STATE.read_text()) if SETUP_STATE.exists() else {}


def _save_state(state: dict) -> None:
    SETUP_STATE.parent.mkdir(exist_ok=True)
    SETUP_STATE.write_text(json.dumps(state, indent=2))


def setup() -> dict:
    """Create (once) the knowledge documents, RAG indexes, client tools and the agent."""
    if not env("ELEVENLABS_API_KEY"):
        raise VoiceUnavailable("Set ELEVENLABS_API_KEY in backend/.env first")
    state = _load_state()
    docs = state.setdefault("documents", {})
    for name, text in knowledge_documents().items():
        if name not in docs:
            docs[name] = _request("POST", "/v1/convai/knowledge-base/text", {"text": text, "name": name})["id"]
            _save_state(state)
    for name, doc_id in docs.items():
        for _ in range(30):  # poll until indexed (small documents index in seconds)
            status = _request("POST", f"/v1/convai/knowledge-base/{doc_id}/rag-index", {"model": RAG_MODEL})["status"]
            if status in ("succeeded", "failed", "rag_limit_exceeded", "document_too_small"):
                break
            time.sleep(2)
        print(f"  {name}: RAG index {status}")
    tools = state.setdefault("tools", {})
    for tool in CLIENT_TOOLS:
        if tool["name"] not in tools:
            tools[tool["name"]] = _request("POST", "/v1/convai/tools", {"tool_config": tool})["id"]
            _save_state(state)
    if "agent_id" not in state:
        body = agent_body(list(tools.values()), [{"id": i, "name": n} for n, i in docs.items()])
        state["agent_id"] = _request("POST", "/v1/convai/agents/create", body)["agent_id"]
        _save_state(state)
    return state


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print what would be created; no API calls")
    ap.add_argument("--setup", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        for name, text in knowledge_documents().items():
            print(f"document {name!r}: {len(text):,} characters")
        for t in CLIENT_TOOLS:
            print(f"client tool {t['name']}")
        print(f"agent 'Pointifly' ({len(AGENT_PROMPT)} character prompt), RAG model {RAG_MODEL}")
        return
    if args.setup:
        state = setup()
        print(f"Agent ready. Add to backend/.env:\nELEVENLABS_AGENT_ID={state['agent_id']}")


if __name__ == "__main__":
    main()
