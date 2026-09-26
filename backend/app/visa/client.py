"""Visa Developer Platform client: two-way SSL (client certificate) + HTTP Basic auth.

Credentials in backend/.env: VISA_USER_ID, VISA_PASSWORD, VISA_CERT_PATH, VISA_KEY_PATH
(certificate and key live in backend/secrets/, which git ignores).
Docs: https://developer.visa.com/pages/working-with-visa-apis/two-way-ssl
"""

import base64
import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path

from ..sources.http import env

BASE_URL = "https://sandbox.api.visa.com"
BACKEND_DIR = Path(__file__).resolve().parents[2]


class VisaError(Exception):
    def __init__(self, status: int, body: str):
        self.status, self.body = status, body
        super().__init__(f"Visa API {status}: {body[:200]}")


def _path(name: str) -> Path | None:
    value = env(name)
    if not value:
        return None
    p = Path(value)
    return p if p.is_absolute() else BACKEND_DIR / p


def configured() -> bool:
    cert, key = _path("VISA_CERT_PATH"), _path("VISA_KEY_PATH")
    return bool(env("VISA_USER_ID") and env("VISA_PASSWORD") and cert and key and cert.exists() and key.exists())


def call(method: str, path: str, body: dict | None = None, timeout: int = 20) -> dict:
    """One API call. Raises VisaError on HTTP errors."""
    ctx = ssl.create_default_context()
    ctx.load_cert_chain(str(_path("VISA_CERT_PATH")), str(_path("VISA_KEY_PATH")))
    auth = base64.b64encode(f"{env('VISA_USER_ID')}:{env('VISA_PASSWORD')}".encode()).decode()
    req = urllib.request.Request(
        BASE_URL + path,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": f"Basic {auth}", "Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            # VMORC text isn't always valid UTF-8; don't fail on a stray byte.
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        raise VisaError(e.code, e.read().decode("utf-8", errors="replace")) from e
