from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import parser, voice

router = APIRouter(prefix="/api")


class ParseRequest(BaseModel):
    sentence: str
    home_airport: str = "ATL"


@router.get("/ai/status")
def status() -> dict:
    return {"parser": parser.configured(), "parser_model": parser.model(), "voice": voice.configured()}


@router.post("/parse")
def parse(req: ParseRequest) -> dict:
    try:
        return parser.parse(req.sentence, req.home_airport)
    except parser.ParseUnavailable as e:
        raise HTTPException(503, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/voice/session")
def voice_session() -> dict:
    """A 15-minute signed link for the browser; the ElevenLabs API key never leaves the server."""
    try:
        return {"signed_url": voice.signed_url()}
    except voice.VoiceUnavailable as e:
        raise HTTPException(503, str(e)) from e
