from __future__ import annotations

import json
import os
import secrets
import stat
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import requests


AUTHORIZE_URL = "https://app.alpaca.markets/oauth/authorize"
TOKEN_URL = "https://api.alpaca.markets/oauth/token"


@dataclass(frozen=True)
class AlpacaOAuthApp:
    client_id: str
    client_secret: str
    redirect_uri: str = "http://127.0.0.1:8765/oauth/callback"

    @classmethod
    def from_env(cls) -> "AlpacaOAuthApp":
        client_id = os.getenv("ALPACA_OAUTH_CLIENT_ID", "")
        client_secret = os.getenv("ALPACA_OAUTH_CLIENT_SECRET", "")
        redirect_uri = os.getenv(
            "ALPACA_OAUTH_REDIRECT_URI",
            "http://127.0.0.1:8765/oauth/callback",
        )
        if not client_id or not client_secret:
            raise RuntimeError(
                "ALPACA_OAUTH_CLIENT_ID and ALPACA_OAUTH_CLIENT_SECRET are required"
            )
        return cls(client_id, client_secret, redirect_uri)


def build_authorization_url(
    app: AlpacaOAuthApp,
    *,
    environment: str = "paper",
    state: str | None = None,
) -> tuple[str, str]:
    if environment not in {"paper", "live"}:
        raise ValueError("environment must be paper or live")
    state = state or secrets.token_urlsafe(32)
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": app.client_id,
            "redirect_uri": app.redirect_uri,
            "state": state,
            "scope": "trading",
            "env": environment,
        }
    )
    return f"{AUTHORIZE_URL}?{query}", state


def exchange_code(app: AlpacaOAuthApp, *, code: str, timeout: float = 15.0) -> dict:
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": app.client_id,
            "client_secret": app.client_secret,
            "redirect_uri": app.redirect_uri,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("access_token"):
        raise RuntimeError("Alpaca token response did not contain access_token")
    return payload


def write_token_file(payload: dict, path: str | Path) -> Path:
    """Persist bearer material outside the repo with owner-only permissions."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(payload, sort_keys=True))
    os.chmod(temp, stat.S_IRUSR | stat.S_IWUSR)
    temp.replace(target)
    os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
    return target
