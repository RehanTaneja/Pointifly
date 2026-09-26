"""Tiny stdlib HTTP + .env helpers shared by the data-source adapters."""

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def env(name: str) -> str | None:
    """Read from the process env, falling back to backend/.env."""
    if name in os.environ:
        return os.environ[name]
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip().strip('"') or None
    return None


def get_json(url: str, params: dict | None = None, headers: dict | None = None, timeout: int = 30):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)
