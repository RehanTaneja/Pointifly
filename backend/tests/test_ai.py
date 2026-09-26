from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.ai import parser, voice
from app.main import app

api = TestClient(app)
TODAY = date.today()
DAY = (TODAY + timedelta(days=60)).isoformat()


def gemini_says(fake_ai, **out):
    fake_ai[0].output = {"balances": [], "trips": [], "unclear": [], **out}


def test_parse_valid_output(fake_ai):
    gemini_says(fake_ai,
        balances=[{"holding": "amex_mr", "points": 100000}, {"holding": "chase_ur", "points": 120000}],
        trips=[{"origin": "ATL", "destination": "CDG", "date": DAY, "date_is_estimate": True, "cabin": "business", "label": "Paris"}])
    r = api.post("/api/parse", json={"sentence": "100k Amex, 120k Chase, Paris in business", "home_airport": "atl"}).json()
    assert r["balances"] == [{"holding": "amex_mr", "points": 100000}, {"holding": "chase_ur", "points": 120000}]
    t = r["trips"][0]
    assert (t["id"], t["label"], t["cabin"], t["date_is_estimate"]) == (f"c-ATL-CDG-{DAY}", "Paris", "business", True)
    assert "ATL" in fake_ai[0].calls[0] and TODAY.isoformat() in fake_ai[0].calls[0]  # context given to the model


def test_invalid_model_output_is_filtered_with_warnings(fake_ai):
    gemini_says(fake_ai,
        balances=[{"holding": "made_up_bank", "points": 5}, {"holding": "united", "points": -3}],
        trips=[{"origin": "ATL", "destination": "ZZZ", "date": DAY, "date_is_estimate": False, "cabin": "economy", "label": "Nowhere"},
               {"origin": "ATL", "destination": "LHR", "date": "2020-01-01", "date_is_estimate": False, "cabin": "economy", "label": "Past"}],
        unclear=["Which Tokyo airport?"])
    r = parser.parse("whatever", "ATL")
    assert r["balances"] == [] and r["trips"] == []
    assert r["warnings"][0] == "Which Tokyo airport?" and len(r["warnings"]) == 3


def test_same_sentence_calls_gemini_once(fake_ai):
    parser.parse("50k Chase", "ATL"); parser.parse("50k Chase", "ATL")
    assert len(fake_ai[0].calls) == 1


def test_parse_errors(fake_ai, monkeypatch):
    assert api.post("/api/parse", json={"sentence": "  "}).status_code == 400
    assert api.post("/api/parse", json={"sentence": "x" * 1001}).status_code == 400
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert api.post("/api/parse", json={"sentence": "50k Chase"}).status_code == 503
    assert fake_ai[0].calls == []


def test_gemini_failure_is_503(fake_ai, monkeypatch):
    def boom(text, schema):
        raise TimeoutError()

    monkeypatch.setattr(parser, "_call", boom)
    r = api.post("/api/parse", json={"sentence": "50k Chase"})
    assert r.status_code == 503 and "TimeoutError" in r.json()["detail"]


def test_schema_limits_holdings_and_cabins():
    s = parser.schema()
    assert "amex_mr" in s["properties"]["balances"]["items"]["properties"]["holding"]["enum"]
    assert s["properties"]["trips"]["items"]["properties"]["cabin"]["enum"] == ["economy", "premium_economy", "business", "first"]


def test_voice_session_signed_url(fake_ai, monkeypatch):
    assert api.get("/api/voice/session").json()["signed_url"].startswith("wss://")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "")
    assert api.get("/api/voice/session").status_code == 503


def test_setup_creates_everything_once(fake_ai):
    state = voice.setup()
    assert state["agent_id"] == "agent_test" and set(state["tools"]) == {"fill_trip_plan", "run_optimizer", "explain_trip"}
    n = len(fake_ai[1].calls)
    voice.setup()  # re-run: only re-checks indexes, creates nothing new
    created = [c for c in fake_ai[1].calls[n:] if c[1] in ("/v1/convai/knowledge-base/text", "/v1/convai/tools", "/v1/convai/agents/create")]
    assert created == []
    agent = next(c[2] for c in fake_ai[1].calls if c[1] == "/v1/convai/agents/create")
    prompt = agent["conversation_config"]["agent"]["prompt"]
    assert prompt["rag"]["enabled"] and len(prompt["knowledge_base"]) == 4 and len(prompt["tool_ids"]) == 3


def test_knowledge_base_holds_only_public_reference_data():
    from pathlib import Path

    text = "\n".join(voice.knowledge_documents().values())
    env = Path(__file__).resolve().parents[1] / ".env"
    secrets = [l.split("=", 1)[1].strip() for l in env.read_text().splitlines() if "=" in l and not l.startswith("#")] if env.exists() else []
    assert not any(s and len(s) > 6 and s in text for s in secrets)  # no keys, ids or passwords
    for private in ("sample_balances", "4111", "points\": ", "PLAID", "VISA_PASSWORD"):
        assert private not in text
    assert "Aeroplan" in text and "Sapphire Preferred" in text


def test_tool_names_match_what_the_browser_registers():
    import re
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "frontend/src/components/VoiceAgent.tsx").read_text()
    for t in voice.CLIENT_TOOLS:
        assert re.search(rf"\b{t['name']}\b", src), t["name"]  # names are case-sensitive on ElevenLabs
