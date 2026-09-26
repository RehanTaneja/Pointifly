"""Natural-language trip parser: one sentence -> point balances + trips, via Gemini.

Gemini returns JSON constrained to a schema; every trip then goes through the same validation
as a hand-entered trip (airports, dates, cabins). Privacy: only the sentence is sent.
Docs: https://ai.google.dev/gemini-api/docs/structured-output
"""

import json
from datetime import date, timedelta

from ..data_store import holding_names
from ..sources.http import env
from ..trips import CABINS, MAX_DAYS_AHEAD, MAX_TRIPS, custom_trip

DEFAULT_MODEL = "gemini-3.5-flash-lite"  # fast, low-cost stable model (override with GEMINI_MODEL)
MAX_SENTENCE = 1000
_CACHE: dict[tuple, dict] = {}  # same sentence + context -> no second API call


class ParseUnavailable(Exception):
    pass


def configured() -> bool:
    return bool(env("GEMINI_API_KEY"))


def model() -> str:
    return env("GEMINI_MODEL") or DEFAULT_MODEL


def schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "balances": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "holding": {"type": "string", "enum": sorted(holding_names())},
                        "points": {"type": "integer"},
                    },
                    "required": ["holding", "points"],
                },
            },
            "trips": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "origin": {"type": "string", "description": "3-letter IATA airport code"},
                        "destination": {"type": "string", "description": "3-letter IATA airport code"},
                        "date": {"type": "string", "description": "YYYY-MM-DD"},
                        "date_is_estimate": {"type": "boolean"},
                        "cabin": {"type": "string", "enum": CABINS},
                        "label": {"type": "string", "description": "Short trip name, usually the city"},
                    },
                    "required": ["origin", "destination", "date", "date_is_estimate", "cabin", "label"],
                },
            },
            "unclear": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["balances", "trips", "unclear"],
    }


def prompt(sentence: str, home_airport: str, today: date) -> str:
    programs = "\n".join(f"- {hid}: {name}" for hid, name in sorted(holding_names().items()))
    return f"""Extract a traveler's point balances and upcoming one-way trips from their sentence.

Today is {today.isoformat()}. Their home airport is {home_airport}.
Rules:
- Balances: map each program mentioned to one of these ids; "100k" means 100000. Only include
  programs the traveler states a number for. Programs:
{programs}
- Trips: one entry per destination. Use the main international airport's IATA code (New York -> JFK,
  London -> LHR, Tokyo -> NRT, Paris -> CDG, Shanghai -> PVG, Beijing -> PEK, Chicago -> ORD), never a
  city code such as NYC, LON, TYO or PAR. Origin is
  {home_airport} unless they say otherwise. Dates must be after today and within {MAX_DAYS_AHEAD} days:
  if only a month is given, use the 15th of its next occurrence and set date_is_estimate true.
- Cabin: economy unless they say premium economy, business or first.
- Never invent balances or trips they didn't mention. Put anything ambiguous in "unclear".

Sentence: {sentence}"""


def _call(text: str, response_schema: dict) -> dict:
    """One Gemini request returning schema-constrained JSON."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=env("GEMINI_API_KEY"))
    resp = client.models.generate_content(
        model=model(),
        contents=text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_json_schema=response_schema, temperature=0
        ),
    )
    return json.loads(resp.text)


def parse(sentence: str, home_airport: str = "ATL", today: date | None = None) -> dict:
    """{balances, trips (validated), warnings, model}. Raises ParseUnavailable without a key."""
    sentence = (sentence or "").strip()
    if not sentence:
        raise ValueError("Say or type your balances and trips first")
    if len(sentence) > MAX_SENTENCE:
        raise ValueError(f"Keep it under {MAX_SENTENCE} characters")
    if not configured():
        raise ParseUnavailable("Trip parsing needs GEMINI_API_KEY in backend/.env")
    today = today or date.today()
    home = home_airport.strip().upper()
    key = (sentence, home, today, model())
    if key in _CACHE:
        return _CACHE[key]
    try:
        raw = _call(prompt(sentence, home, today), schema())
    except Exception as e:  # network, quota or malformed output
        raise ParseUnavailable(f"Gemini request failed ({type(e).__name__})") from e

    known = holding_names()
    warnings = list(raw.get("unclear") or [])
    balances = []
    for b in raw.get("balances") or []:
        if b.get("holding") in known and isinstance(b.get("points"), int) and b["points"] >= 0:
            balances.append({"holding": b["holding"], "points": b["points"]})
    trips = []
    for t in (raw.get("trips") or [])[:MAX_TRIPS]:
        try:
            trip = custom_trip(t["origin"], t["destination"], t["date"], t.get("cabin", "economy"), t.get("label"))
        except (KeyError, ValueError) as e:
            warnings.append(f"Skipped a trip ({t.get('origin')}→{t.get('destination')} {t.get('date')}): {e}")
            continue
        trip["date_is_estimate"] = bool(t.get("date_is_estimate"))
        if all(x["id"] != trip["id"] for x in trips):
            trips.append(trip)
    result = {"balances": balances, "trips": trips, "warnings": warnings, "model": model()}
    _CACHE[key] = result
    return result
